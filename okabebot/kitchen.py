"""Private kitchen ledger. Receipt candidates never become stock without review."""

from contextlib import contextmanager
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re
import time
import uuid
from zoneinfo import ZoneInfo

from .amadeus import Store
from .amadeus_habits import preference
from .amadeus_onboarding import SYSTEM, KEY

DEFAULTS = dict(
    enabled=False,
    proactive=False,
    daily_hour=4,
    expiry_days=3,
    stale_days=30,
    weekdays=["breakfast", "dinner"],
    weekends=["breakfast", "lunch", "dinner"],
    snoozed_until=0,
    allow_eating_out=False,
    eating_out_options=[],
    tastes=[],
    avoid=[],
    coaching=False,
    goals=[],
    planning_days=7,
    timezone="UTC",
    meal_times={"breakfast": 8, "lunch": 12, "dinner": 18},
    suggest_before_hours=2,
)
TABLES = ("kitchen_records", "kitchen_operations")


def text(value, maximum=120):
    if (
        not isinstance(value, str)
        or not 1 <= len(value.strip()) <= maximum
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Use bounded single-line kitchen text")
    return " ".join(value.split())


def canonical(value):
    return " ".join(re.sub(r"[^\w\s]", " ", text(value).casefold()).split())


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100000:
        raise ValueError("Use a finite nonnegative quantity")
    return float(value)


def measure(quantity, unit):
    quantity = number(quantity)
    unit = text(unit, 30).casefold()
    aliases = {
        "grams": "g",
        "gram": "g",
        "kilograms": "kg",
        "kilogram": "kg",
        "liters": "l",
        "liter": "l",
        "milliliters": "ml",
        "milliliter": "ml",
        "pounds": "lb",
        "pound": "lb",
        "ounces": "oz",
        "ounce": "oz",
        "items": "count",
        "item": "count",
        "pcs": "count",
        "cans": "can",
        "bags": "bag",
        "packs": "pack",
    }
    unit = aliases.get(unit, unit)
    target, factor = {
        "kg": ("g", 1000),
        "lb": ("g", 453.59237),
        "oz": ("g", 28.349523125),
        "l": ("ml", 1000),
    }.get(unit, (unit, 1))
    return round(quantity * factor, 6), target


def day(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Use an ISO date")
    return value


def schema(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS kitchen_records (
        subject TEXT NOT NULL, kind TEXT NOT NULL, id TEXT NOT NULL,
        name TEXT NOT NULL, data TEXT NOT NULL, revision INTEGER NOT NULL,
        updated_at REAL NOT NULL, PRIMARY KEY(subject,kind,id));
      CREATE INDEX IF NOT EXISTS kitchen_name ON kitchen_records(subject,kind,name);
      CREATE TABLE IF NOT EXISTS kitchen_operations (
        subject TEXT NOT NULL, id TEXT NOT NULL, fingerprint TEXT NOT NULL,
        result TEXT NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(subject,id));
    """)


def clear(db, subject=None):
    for table in TABLES:
        if db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone():
            db.execute(
                "DELETE FROM " + table + (" WHERE subject=?" if subject else ""),
                (subject,) if subject else (),
            )


def export(store, subject):
    if not store.db.execute("SELECT 1 FROM sqlite_master WHERE name='kitchen_records'").fetchone():
        return []
    return [
        dict(row, data=json.loads(row["data"]))
        for row in store.db.execute(
            "SELECT kind,id,name,data,revision,updated_at FROM kitchen_records WHERE subject=? ORDER BY kind,id",
            (subject,),
        )
    ]


class Kitchen:
    def __init__(self, folder, clock=time.time):
        self.folder, self.clock = Path(folder), clock

    @contextmanager
    def session(self, *, active=False, enabled=False):
        store = Store(self.folder, clock=self.clock)
        try:
            schema(store.db)
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                setup = preference(store, SYSTEM, KEY, {})
                profile = setup.get("profile")
                if (
                    not profile
                    or active
                    and (setup.get("paused") is not False or setup.get("guest") is not False)
                ):
                    raise PermissionError("An active private Amadeus profile is required")
                cfg = {
                    **DEFAULTS,
                    "timezone": setup.get("timezone", "UTC"),
                    **preference(store, profile, "kitchen.settings", {}),
                }
                if enabled and not cfg["enabled"]:
                    raise PermissionError("Enable kitchen assistance in the dashboard first")
                yield store, profile, cfg
        finally:
            store.close()

    @staticmethod
    def rows(store, profile, kind):
        return [
            dict(json.loads(r["data"]), id=r["id"], revision=r["revision"])
            for r in store.db.execute(
                "SELECT * FROM kitchen_records WHERE subject=? AND kind=? ORDER BY name,id",
                (profile, kind),
            )
        ]

    @staticmethod
    def get(store, profile, kind, identity):
        row = store.db.execute(
            "SELECT * FROM kitchen_records WHERE subject=? AND kind=? AND id=?",
            (profile, kind, identity),
        ).fetchone()
        if not row:
            raise ValueError("Kitchen item not found; refresh")
        return dict(json.loads(row["data"]), id=row["id"], revision=row["revision"])

    def put(self, store, profile, kind, value):
        identity = value.get("id") or uuid.uuid4().hex
        old = store.db.execute(
            "SELECT revision FROM kitchen_records WHERE subject=? AND kind=? AND id=?",
            (profile, kind, identity),
        ).fetchone()
        revision = (old[0] if old else 0) + 1
        raw = json.dumps(value, allow_nan=False)
        if len(raw.encode()) > 150000:
            raise ValueError("Kitchen record too large")
        store.db.execute(
            "INSERT INTO kitchen_records VALUES (?,?,?,?,?,?,?) ON CONFLICT(subject,kind,id) DO UPDATE SET name=excluded.name,data=excluded.data,revision=excluded.revision,updated_at=excluded.updated_at",
            (
                profile,
                kind,
                identity,
                canonical(value.get("name") or kind),
                raw,
                revision,
                self.clock(),
            ),
        )
        return dict(value, id=identity, revision=revision)

    def operation(self, store, profile, identity, payload, run):
        text(identity, 160)
        fingerprint = digest(payload)
        previous = store.db.execute(
            "SELECT * FROM kitchen_operations WHERE subject=? AND id=?", (profile, identity)
        ).fetchone()
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise ValueError("Operation ID already used with different contents")
            return json.loads(previous["result"])
        result = run()
        store.db.execute(
            "INSERT INTO kitchen_operations VALUES (?,?,?,?,?)",
            (profile, identity, fingerprint, json.dumps(result), self.clock()),
        )
        return result

    def settings(self, data=None):
        with self.session() as (store, profile, cfg):
            if data is None:
                return cfg
            if not isinstance(data, dict) or set(data) - set(DEFAULTS):
                raise ValueError("Unknown kitchen setting")
            value = {**cfg, **data}
            for k in ("enabled", "proactive", "allow_eating_out", "coaching"):
                if type(value[k]) is not bool:
                    raise ValueError("Use explicit kitchen choices")
            for k, lo, hi in (
                ("daily_hour", 0, 23),
                ("expiry_days", 0, 30),
                ("stale_days", 1, 365),
                ("planning_days", 1, 14),
            ):
                if type(value[k]) is not int or not lo <= value[k] <= hi:
                    raise ValueError("Invalid kitchen schedule or freshness window")
            if (
                not isinstance(value["meal_times"], dict)
                or set(value["meal_times"]) != {"breakfast", "lunch", "dinner"}
                or any(type(v) is not int or not 0 <= v <= 23 for v in value["meal_times"].values())
                or type(value["suggest_before_hours"]) is not int
                or not 0 <= value["suggest_before_hours"] <= 6
            ):
                raise ValueError("Choose meal hours and an advance suggestion window")
            for k in ("weekdays", "weekends"):
                if (
                    not isinstance(value[k], list)
                    or len(set(value[k])) != len(value[k])
                    or any(v not in ("breakfast", "lunch", "dinner") for v in value[k])
                ):
                    raise ValueError("Choose distinct meal slots")
            for k in ("tastes", "avoid", "goals", "eating_out_options"):
                if not isinstance(value[k], list) or len(value[k]) > 40:
                    raise ValueError("Use up to forty explicit choices")
                value[k] = [text(v) for v in value[k]]
            number(
                value["snoozed_until"] / 86400
                if type(value["snoozed_until"]) in (int, float)
                else None
            )
            ZoneInfo(value["timezone"])
            store.remember(profile, "kitchen.settings", value)
            return value

    def snapshot(self, query="", page=1):
        if type(page) is not int or not 1 <= page <= 100000:
            raise ValueError("Use a positive page")
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            query = canonical(query) if query else ""
            # Bound pages, never ingestion. Stable product IDs and normalized-name index.
            rows = store.db.execute(
                "SELECT * FROM kitchen_records WHERE subject=? AND kind='lot' AND instr(name,?)>0 ORDER BY name,id LIMIT 101 OFFSET ?",
                (profile, query, (page - 1) * 100),
            ).fetchall()
            items = [
                dict(
                    json.loads(r["data"]),
                    id=r["id"],
                    revision=r["revision"],
                    stale=self.clock() - json.loads(r["data"])["verified_at"]
                    > cfg["stale_days"] * 86400,
                )
                for r in rows[:100]
            ]
            return dict(
                items=items,
                page=page,
                has_more=len(rows) > 100,
                scope="Explicitly confirmed inventory; quantities/dates may be incomplete. Absence is not proof of no stock.",
            )

    def stage(self, source, external_id, items):
        source, external_id = text(source, 40), text(external_id, 120)
        if not isinstance(items, list) or not 1 <= len(items) <= 500:
            raise ValueError("Import 1–500 candidates per batch; use additional batches for more")
        values = [self.validate_lot(v) for v in items]
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            identity = digest([source, external_id])[:32]
            try:
                previous = self.get(store, profile, "import", identity)
            except ValueError:
                previous = None
            if previous:
                if previous["evidence_hash"] != digest(values):
                    raise ValueError(
                        "This receipt/import ID already has different contents; reconcile it instead"
                    )
                return previous
            return self.put(
                store,
                profile,
                "import",
                dict(
                    id=identity,
                    name=source,
                    source=source,
                    external_id=external_id,
                    evidence_hash=digest(values),
                    items=values,
                    status="review",
                    created_at=self.clock(),
                    possible_duplicates=[
                        v["id"]
                        for v in self.rows(store, profile, "import")
                        if v.get("evidence_hash") == digest(values)
                    ],
                ),
            )

    @staticmethod
    def validate_lot(value):
        if not isinstance(value, dict) or set(value) - {
            "name",
            "quantity",
            "unit",
            "location",
            "best_by",
            "date_kind",
            "confidence",
            "long_lasting",
            "product_id",
        }:
            raise ValueError(
                "Use ingredient, quantity, unit, storage location and optional printed date"
            )
        name = text(value.get("name"))
        amount, unit = measure(value.get("quantity", 1), value.get("unit", "count"))
        return dict(
            name=name,
            product_id=digest(canonical(name))[:24],
            quantity=amount,
            unit=unit,
            location=text(value.get("location", "pantry"), 60),
            best_by=day(value.get("best_by")),
            date_kind=value.get("date_kind", "unknown")
            if value.get("date_kind", "unknown") in ("unknown", "best_by", "use_by", "estimated")
            else "unknown",
            confidence=value.get("confidence", "needs_check")
            if value.get("confidence") in ("confirmed", "probable", "needs_check")
            else "needs_check",
            long_lasting=value.get("long_lasting") is True,
        )

    def confirm(self, identity, revision, items, operation_id):
        values = [self.validate_lot(v) for v in items]
        if not 1 <= len(values) <= 500:
            raise ValueError("Confirm 1–500 reviewed ingredients")
        payload = dict(id=identity, revision=revision, items=values)
        with self.session(active=True, enabled=True) as (store, profile, cfg):

            def run():
                batch = self.get(store, profile, "import", identity)
                if (
                    batch["status"] != "review"
                    or type(revision) is not int
                    or batch["revision"] != revision
                ):
                    raise ValueError("Import changed or already confirmed; refresh")
                ids = []
                for i, value in enumerate(values):
                    product = dict(id=value["product_id"], name=value["name"])
                    self.put(store, profile, "product", product)
                    lot = self.put(
                        store,
                        profile,
                        "lot",
                        dict(
                            value,
                            id=digest([identity, i])[:32],
                            evidence_id=identity,
                            confidence="confirmed",
                            verified_at=self.clock(),
                            status="available" if value["quantity"] else "empty",
                        ),
                    )
                    ids.append(lot["id"])
                self.put(
                    store, profile, "import", dict(batch, status="confirmed", items=[], lot_ids=ids)
                )
                return dict(confirmed=len(ids), lot_ids=ids)

            return self.operation(store, profile, operation_id, payload, run)

    def adjust(self, identity, revision, quantity, operation_id, action="correct"):
        quantity = number(quantity)
        if action not in ("correct", "consume", "discard", "verify"):
            raise ValueError("Choose a supported inventory movement")
        with self.session(active=True, enabled=True) as (store, profile, cfg):

            def run():
                lot = self.get(store, profile, "lot", identity)
                if type(revision) is not int or lot["revision"] != revision:
                    raise ValueError("Stock changed; refresh before adjusting")
                remaining = (
                    lot["quantity"] - quantity if action in ("consume", "discard") else quantity
                )
                if remaining < 0:
                    raise ValueError("Cannot consume more than recorded stock")
                updated = self.put(
                    store,
                    profile,
                    "lot",
                    dict(
                        lot,
                        quantity=remaining,
                        status="available" if remaining else "empty",
                        verified_at=self.clock(),
                    ),
                )
                self.put(
                    store,
                    profile,
                    "movement",
                    dict(
                        name=action,
                        lot_id=identity,
                        before=lot["quantity"],
                        after=remaining,
                        at=self.clock(),
                        operation_id=operation_id,
                    ),
                )
                return updated

            return self.operation(
                store,
                profile,
                operation_id,
                dict(id=identity, revision=revision, quantity=quantity, action=action),
                run,
            )

    def dashboard(self):
        with self.session() as (store, profile, cfg):
            return dict(
                settings=cfg,
                products=self.rows(store, profile, "product"),
                imports=self.rows(store, profile, "import"),
                recipes=self.rows(store, profile, "recipe"),
                plans=self.rows(store, profile, "plan"),
                shopping=self.rows(store, profile, "shopping"),
                index=self.rows(store, profile, "index"),
                browser_jobs=self.rows(store, profile, "browser_job"),
            )

    def presentation(self):
        try:
            with self.session(active=True, enabled=True) as (store, profile, cfg):
                jobs = self.rows(store, profile, "browser_job")
                for job in jobs:
                    status = job["status"]
                    start = job.get("ready_at", job.get("started_at", 0))
                    if (
                        status in ("searching", "transferring", "review")
                        and 0 <= self.clock() - start < 180
                    ):
                        return dict(
                            kind="shopping_list",
                            stage={
                                "searching": "researching",
                                "transferring": "drafting",
                                "review": "awaiting_review",
                            }[status],
                            elapsed_seconds=self.clock() - start,
                            lease_seconds=8,
                        )
        except PermissionError:
            pass
        return {}

    def tag(self, product_id, action, quantity, unit, event_id):
        if action not in ("kitchen_used_up", "kitchen_reorder") or not event_id:
            raise ValueError("A mapped real scan is required")
        quantity = number(quantity)
        unit = text(unit, 30).casefold()
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            product = self.get(store, profile, "product", product_id)

            def run():
                if action == "kitchen_used_up":
                    for lot in self.rows(store, profile, "lot"):
                        if lot["product_id"] == product_id and lot["quantity"]:
                            self.put(
                                store,
                                profile,
                                "movement",
                                dict(
                                    name="used_up_tag",
                                    lot_id=lot["id"],
                                    before=lot["quantity"],
                                    after=0,
                                    at=self.clock(),
                                ),
                            )
                            self.put(
                                store,
                                profile,
                                "lot",
                                dict(lot, quantity=0, status="empty", verified_at=self.clock()),
                            )
                else:
                    try:
                        draft = self.get(store, profile, "shopping", "nfc")
                    except ValueError:
                        draft = dict(
                            id="nfc",
                            name="NFC shopping additions",
                            items=[],
                            status="review",
                            provider="local",
                        )
                    items = draft["items"]
                    found = next(
                        (
                            v
                            for v in items
                            if canonical(v["name"]) == canonical(product["name"])
                            and v["unit"] == unit
                        ),
                        None,
                    )
                    if found:
                        found["quantity"] += quantity
                    else:
                        items.append(dict(name=product["name"], quantity=quantity, unit=unit))
                    self.put(
                        store,
                        profile,
                        "shopping",
                        dict(draft, items=items, created_at=self.clock()),
                    )
                return {
                    "status": "ingredient_marked_used_up"
                    if action == "kitchen_used_up"
                    else "added_to_local_shopping_draft"
                }

            return self.operation(
                store,
                profile,
                "nfc:" + event_id,
                dict(product_id=product_id, action=action, quantity=quantity, unit=unit),
                run,
            )

    def erase(self):
        with self.session() as (store, profile, cfg):
            clear(store.db, profile)
            store.db.execute(
                "DELETE FROM preferences WHERE subject=? AND key LIKE 'kitchen.%'", (profile,)
            )
        return {"deleted": True}

    def today(self, cfg):
        return datetime.fromtimestamp(self.clock(), ZoneInfo(cfg["timezone"])).date()
