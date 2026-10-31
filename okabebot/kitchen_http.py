"""Owner kitchen routes; mobile may query through read tools, never approve a cart."""

import json
from urllib.parse import urlsplit, parse_qs

from .kitchen_import import parse, ocr_image


ACTIONS = {
    "settings",
    "import",
    "confirm",
    "adjust",
    "recipes",
    "plan",
    "index",
    "snooze",
    "erase",
    "shopping-search",
    "shopping-review",
    "shopping-approve",
    "shopping-cancel",
    "browser",
    "export",
}


def handle(handler, bridge, post=False):
    url = urlsplit(handler.path)
    if url.path not in ("/kitchen", "/kitchen/ingredients") and not (
        url.path.startswith("/kitchen/") and url.path.split("/")[-1] in ACTIONS
    ):
        return False
    origin = handler.headers.get("Origin")
    if (
        handler.headers.get("Host") not in bridge.allowed_hosts
        or not handler.authorized()
        or origin
        and urlsplit(origin).netloc != handler.headers.get("Host")
    ):
        handler.respond(403, {"error": "Owner kitchen access required"})
        return True
    try:
        from .kitchen_planning import Planner
        from .kitchen_shopping import Shopping
        from .kitchen_browser import Browser

        kitchen = getattr(bridge, "kitchen", None) or Planner(bridge.preparations.folder)
        data = {}
        if post:
            size = int(handler.headers.get("Content-Length", 0))
            if not 0 < size <= 12_500_000:
                raise ValueError("Invalid kitchen request size")
            handler.connection.settimeout(10)
            data = json.loads(handler.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError("Use a kitchen request object")
        action = url.path.rsplit("/", 1)[-1]
        if not post:
            if url.path == "/kitchen":
                result = kitchen.dashboard()
                result["browser"] = Browser(kitchen.folder).configure()
            elif action == "ingredients":
                params = parse_qs(url.query)
                result = kitchen.snapshot(
                    params.get("query", [""])[0], int(params.get("page", [1])[0])
                )
            elif action == "export":
                from .kitchen import export

                with kitchen.session() as (store, profile, cfg):
                    result = {"records": export(store, profile), "settings": cfg}
            else:
                raise ValueError("Use POST for kitchen actions")
        elif action == "settings":
            result = kitchen.settings(data)
        elif action == "import":
            items = data.get("items")
            if items is None:
                raw = ocr_image(data["image"]) if data.get("image") else data.get("text", "")
                items = parse(raw, data.get("format", "text"), data.get("long_lasting") is True)
            from .kitchen import digest

            external_id = data.get("external_id") or digest(
                [data["source"], data.get("image") or data.get("text") or items]
            )
            result = kitchen.stage(data["source"], external_id, items)
        elif action == "confirm":
            result = kitchen.confirm(
                data["id"], data["revision"], data["items"], data["operation_id"]
            )
        elif action == "adjust":
            result = kitchen.adjust(
                data["id"],
                data["revision"],
                data["quantity"],
                data["operation_id"],
                data.get("action", "correct"),
            )
        elif action == "recipes":
            if data == {"starter": True}:
                from pathlib import Path

                items = json.loads(
                    (Path(__file__).parent / "assets/kitchen-recipes.json").read_text()
                )
            else:
                items = data["items"]
            result = kitchen.import_recipes(items)
        elif action == "plan":
            result = kitchen.generate()
        elif action == "index":
            result = kitchen.index(force=True)
        elif action == "snooze":
            hours = data["hours"]
            if type(hours) is not int or not 0 <= hours <= 24 * 30:
                raise ValueError("Snooze from 0 hours to 30 days")
            result = kitchen.settings({"snoozed_until": kitchen.clock() + hours * 3600})
        elif action == "erase" and data == {"confirm": "erase_kitchen"}:
            result = kitchen.erase()
        elif action == "browser":
            result = Browser(kitchen.folder).configure(data)
        elif action.startswith("shopping-"):
            shop = Shopping(kitchen.folder)
            if action == "shopping-cancel":
                result = shop.cancel(data["id"], data["revision"])
            elif action == "shopping-search":
                result = shop.queue(data["id"], data["revision"])
            elif action == "shopping-review":
                result = shop.review(data["id"], data["revision"], data["products"])
            else:
                result = shop.approve(data["id"], data["revision"], data["manifest_hash"])
        else:
            raise ValueError("Unknown kitchen action")
        handler.respond(200, result)
    except PermissionError as exc:
        handler.respond(403, {"error": str(exc)})
    except (ValueError, KeyError, TypeError) as exc:
        handler.respond(400, {"error": str(exc)})
    except Exception:
        handler.respond(
            503,
            {
                "error": "Kitchen operation unavailable; refresh before retrying. No automatic retry."
            },
        )
    return True
