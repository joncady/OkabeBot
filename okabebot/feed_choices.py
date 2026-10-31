"""Semantic discovery hints, never observation consent or proof of upstream identity."""

import re


def hints(identity, entity, state, device):
    attrs = state.get("attributes", {})
    text = " ".join(
        str(v or "")
        for v in (
            identity,
            entity.get("unique_id"),
            entity.get("original_name"),
            entity.get("name"),
            attrs.get("friendly_name"),
        )
    ).lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    platform = str(entity.get("platform", "")).lower()
    model = str(device.get("model", "")).lower()
    unit = str(attrs.get("unit_of_measurement", ""))[:40]
    kind = str(
        attrs.get("device_class")
        or entity.get("device_class")
        or entity.get("original_device_class")
        or ""
    )[:60]
    health_connect = "health_connect" in text
    wear = platform == "mobile_app" and (
        "watch" in model or "watch" in text or "watch" in str(device.get("name", "")).lower()
    )
    fields = []

    def add(feed, key):
        fields.append(feed + "." + key)

    if identity.startswith("person."):
        add("presence_history", "persons")
    if identity.startswith("zone."):
        add("presence_history", "zones")

    if identity.startswith("sensor."):
        if unit.lower() in ("step", "steps") and "step" in text and "daily" in text:
            add("health", "daily_steps")
        if unit.lower() in ("min", "minutes"):
            if re.search(r"(?:^|_)sleep_duration(?:_|$)", text):
                add("health", "sleep_minutes")
            if "daily" in text and any(
                w in text for w in ("active_minutes", "exercise_duration", "activity_duration")
            ):
                add("health", "active_minutes")
        if (
            kind == "temperature"
            or any(w in text for w in ("temperature", "thermostat", "hvac"))
            or platform in ("watts_home", "aladdin_connect")
        ):
            add("home_devices", "sensors")
        if (
            platform in ("smartthinq_sensors", "lg_thinq", "thinq")
            or str(device.get("manufacturer", "")).lower() == "lg"
        ):
            add("appliances", "entities")
    if identity.startswith("binary_sensor."):
        for key, terms in {
            "charging": ("charging",),
            "focus": ("focus", "do_not_disturb", "dnd"),
            "locked": ("device_locked", "device_lock", "locked"),
            "screen": ("interactive", "screen_on", "display_awake", "screen_state"),
        }.items():
            if any(w in text for w in terms):
                add("device_activity", key)
        if kind in ("occupancy", "presence", "motion") or any(
            w in text
            for w in (
                "occupancy",
                "presence",
                "guest_present",
                "visitor_present",
                "others_detected",
            )
        ):
            add("health", "others")
    if identity.startswith("calendar.") and (platform == "mealie" or "meal" in text):
        add("meals", "calendars")
    if identity.startswith("todo.") and (
        platform == "mealie" or any(w in text for w in ("shopping", "grocery", "groceries"))
    ):
        add("meals", "shopping")
    return {
        "unit": unit,
        "device_class": kind,
        "feed_fields": fields,
        "health_source": "Health Connect · upstream app not verified"
        if health_connect
        else "Watch app · direct sensor"
        if wear
        else "Phone hardware · since reboot"
        if "steps_sensor" in text
        else "HA sensor · verify daily total"
        if any(f.startswith("health.") and not f.endswith("others") for f in fields)
        else "",
    }
