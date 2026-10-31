"""Durable asynchronous shopping jobs. Search is separate from approved cart writes.

No checkout capability is exposed. A crash after a write starts is unknown, never
an automatic retry. Browser adapters receive only the approved exact product rows.
"""

import uuid

from .kitchen import Kitchen, digest, text
from .amadeus_habits import preference


def consent(store, profile, cfg):
    return digest({"settings": cfg, "browser": preference(store, profile, "kitchen.browser", {})})


class Shopping(Kitchen):
    def queue(self, draft_id, revision):
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            draft = self.get(store, profile, "shopping", draft_id)
            if type(revision) is not int or draft["revision"] != revision or not draft["items"]:
                raise ValueError("Refresh a nonempty shopping draft")
            identity = digest([draft_id, revision])[:32]
            try:
                return self.get(store, profile, "browser_job", identity)
            except ValueError:
                pass
            return self.put(
                store,
                profile,
                "browser_job",
                dict(
                    id=identity,
                    name="Safeway preparation",
                    draft_id=draft_id,
                    draft_revision=revision,
                    items=draft["items"],
                    status="queued",
                    products=[],
                    created_at=self.clock(),
                    consent_hash=consent(store, profile, cfg),
                ),
            )

    def review(self, identity, revision, products):
        if not isinstance(products, list) or not 1 <= len(products) <= 100:
            raise ValueError("Review 1–100 exact products")
        normalized = []
        for row in products:
            if not isinstance(row, dict) or set(row) != {
                "product_id",
                "name",
                "price_cents",
                "packs",
                "requested_name",
            }:
                raise ValueError("Exact product identity, price and package count are required")
            if (
                type(row["price_cents"]) is not int
                or not 0 < row["price_cents"] <= 100000
                or type(row["packs"]) is not int
                or not 1 <= row["packs"] <= 20
            ):
                raise ValueError("Review price and package quantity")
            normalized.append(
                {
                    **row,
                    "name": text(row["name"]),
                    "product_id": text(row["product_id"], 80),
                    "requested_name": text(row["requested_name"]),
                }
            )
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            job = self.get(store, profile, "browser_job", identity)
            if job["revision"] != revision or job["status"] not in (
                "queued",
                "searching",
                "review",
            ):
                raise ValueError("Shopping work changed; refresh")
            draft = self.get(store, profile, "shopping", job["draft_id"])
            if draft["revision"] != job["draft_revision"] or job["consent_hash"] != consent(
                store, profile, cfg
            ):
                raise ValueError("Shopping draft or configuration changed")
            requested = {v["name"] for v in job["items"]}
            if any(v["requested_name"] not in requested for v in normalized):
                raise ValueError("Products must refer to the requested list")
            return self.put(
                store,
                profile,
                "browser_job",
                dict(
                    job,
                    status="review",
                    ready_at=self.clock(),
                    products=normalized,
                    total_cents=sum(v["price_cents"] * v["packs"] for v in normalized),
                    manifest_hash=digest(normalized),
                ),
            )

    def approve(self, identity, revision, manifest_hash):
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            job = self.get(store, profile, "browser_job", identity)
            draft = self.get(store, profile, "shopping", job["draft_id"])
            if (
                type(revision) is not int
                or job["revision"] != revision
                or job["status"] != "review"
                or job.get("manifest_hash") != manifest_hash
                or draft["revision"] != job["draft_revision"]
            ):
                raise ValueError("Review the current exact products before approving")
            return self.put(
                store,
                profile,
                "browser_job",
                dict(
                    job,
                    status="approved",
                    approved_until=self.clock() + 900,
                    consent_hash=consent(store, profile, cfg),
                    operation_id=uuid.uuid4().hex,
                ),
            )

    def cancel(self, identity, revision):
        with self.session() as (store, profile, cfg):
            job = self.get(store, profile, "browser_job", identity)
            if type(revision) is not int or job["revision"] != revision:
                raise ValueError("Shopping work changed; refresh")
            if job["status"] in ("complete", "unknown", "canceled"):
                raise ValueError("Check the current cart; this job cannot be retried")
            return self.put(
                store,
                profile,
                "browser_job",
                dict(
                    job,
                    status="unknown" if job["status"] == "transferring" else "canceled",
                    reason="Owner canceled; check cart if a transfer had started",
                ),
            )

    def run(self, adapter):
        # Persist claim before any browser effect. No ongoing DB transaction during I/O.
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            jobs = self.rows(store, profile, "browser_job")
            interrupted = [
                v
                for v in jobs
                if v["status"] in ("searching", "transferring")
                and self.clock() - v.get("started_at", 0) > 180
            ]
            for v in interrupted:
                self.put(
                    store,
                    profile,
                    "browser_job",
                    dict(
                        v,
                        status="unknown" if v["status"] == "transferring" else "blocked",
                        reason="worker_interrupted_check_before_retry",
                    ),
                )
            job = next((v for v in jobs if v["status"] in ("queued", "approved")), None)
            if not job:
                return {"state": "idle"}
            phase = "searching" if job["status"] == "queued" else "transferring"
            draft = self.get(store, profile, "shopping", job["draft_id"])
            if (
                job["consent_hash"] != consent(store, profile, cfg)
                or draft["revision"] != job["draft_revision"]
                or phase == "transferring"
                and self.clock() >= job.get("approved_until", 0)
            ):
                return self.put(
                    store,
                    profile,
                    "browser_job",
                    dict(job, status="blocked", reason="configuration_draft_or_approval_changed"),
                )
            job = self.put(
                store, profile, "browser_job", dict(job, status=phase, started_at=self.clock())
            )
        try:
            if phase == "searching":
                products = adapter.search(job["items"])
                return self.review(job["id"], job["revision"], products)
            for product in job["products"]:
                for _ in range(product["packs"]):
                    with self.session(active=True, enabled=True) as (store, p, cfg):
                        current = self.get(store, p, "browser_job", job["id"])
                        draft = self.get(store, p, "shopping", job["draft_id"])
                        if (
                            p != profile
                            or current["status"] != "transferring"
                            or consent(store, p, cfg) != job["consent_hash"]
                            or self.clock() >= job["approved_until"]
                            or draft["revision"] != job["draft_revision"]
                        ):
                            raise PermissionError("Shopping approval changed")
                    # Recheck cancellation/consent before each individual package write.
                    adapter.add_exact({**product, "packs": 1})
            status, reason = "complete", "Cart prepared; checkout remains manual"
        except Exception:
            status, reason = (
                ("unknown" if phase == "transferring" else "blocked"),
                "Check browser/account state before retrying; no automatic retry",
            )
        with self.session() as (store, p, cfg):
            # Never recreate forgotten/private state after an in-flight browser call.
            if p != profile:
                return {"state": "context_changed"}
            try:
                current = self.get(store, p, "browser_job", job["id"])
            except ValueError:
                return {"state": "context_changed"}
            if current["status"] != phase:
                return current
            return self.put(store, p, "browser_job", dict(current, status=status, reason=reason))
