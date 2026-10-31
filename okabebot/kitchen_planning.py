"""Grounded meal ranking and durable shopping drafts, not nutritional or safety advice."""

from datetime import date as Date, datetime, timedelta
from zoneinfo import ZoneInfo

from .amadeus_habits import preference

from .kitchen import Kitchen, canonical, text, number, day, digest, measure


def recipe(value):
    if not isinstance(value, dict):
        raise ValueError("Use a structured recipe")
    name = text(value.get("name"))
    ingredients = value.get("ingredients", value.get("recipeIngredient", []))
    if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 100:
        raise ValueError("Use 1–100 structured recipe ingredients")
    normalized = []
    for v in ingredients:
        if not isinstance(v, dict):
            raise ValueError(
                "Mealie ingredients need food names and known quantity/unit, not free-text inference"
            )
        food = v.get("food") or {}
        unit = v.get("unit") or "count"
        if isinstance(unit, dict):
            unit = unit.get("name", "count")
        name_value = v.get("name") or (food.get("name") if isinstance(food, dict) else food)
        amount, unit = measure(v.get("quantity"), unit)
        if amount <= 0:
            raise ValueError("Recipe quantities must be positive")
        normalized.append(
            dict(
                name=text(name_value),
                quantity=amount,
                unit=unit,
            )
        )
    tags = value.get("tags", [])
    tags = [v.get("name") if isinstance(v, dict) else v for v in tags]
    slots = value.get("meals", ["breakfast", "lunch", "dinner"])
    if (
        not isinstance(slots, list)
        or not slots
        or any(v not in ("breakfast", "lunch", "dinner") for v in slots)
    ):
        raise ValueError("Choose recipe meal slots")
    minutes = number(value.get("minutes", 30))
    return dict(
        id=digest(["recipe", canonical(name)])[:32],
        name=name,
        ingredients=normalized,
        tags=[text(v, 60).casefold() for v in tags],
        meals=slots,
        minutes=minutes,
    )


class Planner(Kitchen):
    def import_recipes(self, values):
        if not isinstance(values, list) or not 1 <= len(values) <= 500:
            raise ValueError("Import 1–500 recipes per batch")
        values = [recipe(v) for v in values]
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            return dict(recipes=[self.put(store, profile, "recipe", v) for v in values])

    def candidates(self, store, profile, cfg, date, meal, reserved=None):
        reserved = reserved or {}
        lots = self.rows(store, profile, "lot")
        recipes = self.rows(store, profile, "recipe")
        today = self.today(cfg)
        stocks = {}
        due = {}
        for lot in lots:
            if (
                lot["quantity"] <= 0
                or self.clock() - lot["verified_at"] > cfg["stale_days"] * 86400
            ):
                continue
            # Past printed dates need human checking; no automatic food safety judgment.
            if lot.get("best_by") and lot["best_by"] < date:
                continue
            key = (canonical(lot["name"]), lot["unit"])
            stocks[key] = stocks.get(key, 0) + lot["quantity"]
            if (
                lot.get("best_by")
                and lot["best_by"] <= (today + timedelta(days=cfg["expiry_days"])).isoformat()
            ):
                due[key] = lot["best_by"]
        for key, quantity in reserved.items():
            stocks[key] = max(0, stocks.get(key, 0) - quantity)
        avoid = {canonical(v) for v in cfg["avoid"]}
        saved = preference(store, profile, "context.preferences", {})
        saved_tastes = saved.get("food_drink", [])
        tastes = {
            canonical(v)
            for v in cfg["tastes"]
            + [v[:120] for v in saved_tastes if isinstance(v, str) and v.strip()]
        }
        from .amadeus_health import others_detected

        goals = set()
        if cfg["coaching"] and not others_detected(store):
            goals = {canonical(v) for v in cfg["goals"]}
            coaching = preference(store, profile, "health.coaching", {})
            if coaching.get("enabled") and "meals" in coaching.get("topics", []):
                goals.update(
                    canonical(v) for v in saved.get("personal_goals", []) if isinstance(v, str)
                )
        result = []
        for r in recipes:
            if meal not in r["meals"]:
                continue
            labels = {canonical(v["name"]) for v in r["ingredients"]} | {
                canonical(v) for v in r["tags"]
            }
            if avoid & labels:
                continue
            missing = []
            using = []
            coverage = 0
            needs = {}
            for ingredient in r["ingredients"]:
                key = (canonical(ingredient["name"]), ingredient["unit"])
                needs[key] = needs.get(key, 0) + ingredient["quantity"]
            for key, amount in needs.items():
                have = min(amount, stocks.get(key, 0))
                coverage += have / amount if amount else 1
                if have < amount:
                    missing.append(dict(name=key[0], quantity=round(amount - have, 4), unit=key[1]))
                if have and key in due:
                    using.append(dict(name=key[0], best_by=due[key]))
            taste = sorted(tastes & labels)
            result.append(
                dict(
                    id=r["id"],
                    name=r["name"],
                    minutes=r["minutes"],
                    ingredients=r["ingredients"],
                    missing=missing,
                    use_soon=using,
                    taste_matches=taste,
                    score=round(
                        coverage / max(1, len(needs)) * 10
                        + len(using) * 4
                        + len(taste) * 2
                        + len(goals & labels) * 2,
                        2,
                    ),
                    reason=(
                        "Uses recorded ingredients"
                        if coverage
                        else "Needs a shopping trip for this saved recipe"
                    )
                    + (" including items with upcoming dates" if using else "")
                    + (" and matches explicit tastes" if taste else ""),
                )
            )
        return sorted(result, key=lambda v: (-v["score"], v["name"]))

    def suggest(self, meal="dinner", on=None):
        if meal not in ("breakfast", "lunch", "dinner"):
            raise ValueError("Choose a meal")
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            on = day(on) or self.today(cfg).isoformat()
            from .amadeus_health import others_detected

            goals = cfg["goals"] if cfg["coaching"] and not others_detected(store) else []
            return dict(
                date=on,
                meal=meal,
                suggestions=self.candidates(store, profile, cfg, on, meal)[:8],
                eating_out=cfg["eating_out_options"] if cfg["allow_eating_out"] else [],
                coaching_goals=goals,
                scope="Recorded stock and explicit recipe/taste tags only. Avoid list is exact ingredient/tag matching, not an allergen guarantee. Verify labels, dates and quantities; no medical/nutrition inference.",
            )

    def generate(self, key=None):
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            today = self.today(cfg)
            identity = key or today.isoformat()
            reserved = {}
            slots = []
            shopping = {}
            picked = {}
            for offset in range(cfg["planning_days"]):
                date = today + timedelta(days=offset)
                for meal in cfg["weekdays"] if date.weekday() < 5 else cfg["weekends"]:
                    choices = self.candidates(store, profile, cfg, date.isoformat(), meal, reserved)
                    # Prefer variety after grounding/expiry, without inventing missing recipes.
                    choices.sort(
                        key=lambda v: (-(v["score"] - picked.get(v["id"], 0) * 3), v["name"])
                    )
                    if not choices:
                        slots.append(dict(date=date.isoformat(), meal=meal, state="recipe_needed"))
                        continue
                    chosen = choices[0]
                    picked[chosen["id"]] = picked.get(chosen["id"], 0) + 1
                    slots.append(
                        dict(date=date.isoformat(), meal=meal, state="proposed", recipe=chosen)
                    )
                    for ingredient in chosen["ingredients"]:
                        k = (canonical(ingredient["name"]), ingredient["unit"])
                        reserved[k] = reserved.get(k, 0) + ingredient["quantity"]
                    for missing in chosen["missing"]:
                        k = (missing["name"], missing["unit"])
                        shopping[k] = shopping.get(k, 0) + missing["quantity"]
            # Missing amounts are incremental, since reservations include earlier shortages.
            plan = self.put(
                store,
                profile,
                "plan",
                dict(
                    id=identity,
                    name="Meal plan",
                    created_at=self.clock(),
                    slots=slots,
                    status="proposed",
                ),
            )
            draft = self.put(
                store,
                profile,
                "shopping",
                dict(
                    id=identity,
                    name="Next shopping trip",
                    created_at=self.clock(),
                    items=[
                        dict(name=k[0], unit=k[1], quantity=round(v, 4))
                        for k, v in sorted(shopping.items())
                    ],
                    status="review",
                    provider="local",
                    plan_id=identity,
                ),
            )
            return dict(plan=plan, shopping=draft)

    def due(self, store, profile, cfg):
        today = self.today(cfg)
        return [
            dict(v, days_until=(Date.fromisoformat(v["best_by"]) - today).days)
            for v in self.rows(store, profile, "lot")
            if v["quantity"] > 0
            and v.get("best_by")
            and v["best_by"] <= (today + timedelta(days=cfg["expiry_days"])).isoformat()
        ]

    def index(self, force=False):
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            today = self.today(cfg)
            identity = today.isoformat()
            local = datetime.fromtimestamp(self.clock(), ZoneInfo(cfg["timezone"]))
            if not force and local.hour < cfg["daily_hour"]:
                return {"state": "not_due"}
            try:
                existing = self.get(store, profile, "index", identity)
                if not force and not existing.get("plan_pending"):
                    return existing
            except ValueError:
                pass
            lots = self.rows(store, profile, "lot")
            result = self.put(
                store,
                profile,
                "index",
                dict(
                    id=identity,
                    name="Daily kitchen index",
                    at=self.clock(),
                    lot_count=len(lots),
                    due=[
                        {k: v[k] for k in ("id", "revision", "best_by")}
                        for v in self.due(store, profile, cfg)
                    ],
                    stale_ids=[
                        v["id"]
                        for v in lots
                        if self.clock() - v["verified_at"] > cfg["stale_days"] * 86400
                    ],
                    state="indexed",
                    plan_pending=True,
                ),
            )
        # Outside the first transaction; crash leaves a resumable pending daily index.
        generated = self.generate(identity)
        from .kitchen_browser import Browser

        if (
            Browser(self.folder, clock=self.clock).configure()["enabled"]
            and generated["shopping"]["items"]
        ):
            from .kitchen_shopping import Shopping

            Shopping(self.folder, clock=self.clock).queue(
                generated["shopping"]["id"], generated["shopping"]["revision"]
            )
        with self.session(active=True, enabled=True) as (store, profile, cfg):
            return self.put(
                store,
                profile,
                "index",
                dict(result, plan_pending=False, plan_id=generated["plan"]["id"]),
            )

    def pending(self, store, profile, cfg):
        if not cfg["enabled"] or not cfg["proactive"] or cfg["snoozed_until"] > self.clock():
            return None
        day = self.today(cfg).isoformat()
        due = self.due(store, profile, cfg)
        plans = self.rows(store, profile, "plan")
        today = next((v for v in plans if v["id"] == day), None)
        delivered = preference(store, profile, "kitchen.delivered", {})
        if delivered.get("expiry_day") == day:
            due = []
        local = datetime.fromtimestamp(self.clock(), ZoneInfo(cfg["timezone"]))
        clock_hour = local.hour + local.minute / 60
        meals = [
            v
            for v in (today or {}).get("slots", [])
            if v["date"] == day
            and v.get("recipe")
            and cfg["meal_times"][v["meal"]] - cfg["suggest_before_hours"]
            <= clock_hour
            < cfg["meal_times"][v["meal"]] + 1
            and day + ":" + v["meal"] not in delivered.get("slots", {})
        ]
        if not due and not meals:
            return None
        slot = day + ":" + meals[0]["meal"] if meals else None
        fingerprint = digest(
            [
                day,
                slot,
                [(v["id"], v["revision"]) for v in due],
                today.get("revision") if today else None,
            ]
        )
        return dict(
            id=fingerprint,
            day=day,
            slot=slot,
            due=[
                dict(name=v["name"], best_by=v["best_by"], days_until=v["days_until"])
                for v in due[:3]
            ],
            meals=[dict(meal=v["meal"], name=v["recipe"]["name"]) for v in meals[:1]],
        )

    def offer(self):
        try:
            with self.session(active=True, enabled=True) as (store, profile, cfg):
                return self.pending(store, profile, cfg)
        except PermissionError:
            return None

    @staticmethod
    def offer_text(offer):
        parts = []
        if offer.get("due"):
            parts.append(
                "A kitchen note: check the recorded dates and condition of "
                + ", ".join(v["name"] for v in offer["due"])
                + "; those dates are near or past, so check the items before using them."
            )
        if offer.get("meals"):
            parts.append(
                "One option for today is "
                + offer["meals"][0]["name"]
                + ". The meal plan and missing ingredients are ready to review."
            )
        return " ".join(parts)
