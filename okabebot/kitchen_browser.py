"""Optional bounded Playwright Safeway adapter. Never exposes checkout to a model.

A private, owner-configured selector contract is required because retailer markup
and fulfillment availability vary. Missing/ambiguous fields stop the job. Login is
interactive; no passwords/cookies are copied into Amadeus prompts or logs.
"""

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import quote, urlsplit

from .kitchen import Kitchen, text

FIELDS = (
    "card",
    "name",
    "price",
    "product_id_attribute",
    "add",
    "cart_count",
    "store",
    "expected_store",
)


def money(value):
    match = re.fullmatch(r"\s*\$?(\d+(?:\.\d{2})?)\s*", value)
    if not match:
        raise ValueError("Ambiguous retailer price")
    try:
        return int(Decimal(match[1]) * 100)
    except InvalidOperation:
        raise ValueError("Invalid price") from None


class Browser(Kitchen):
    def configure(self, value=None):
        with self.session() as (store, profile, cfg):
            from .amadeus_habits import preference

            if value is not None:
                if (
                    not isinstance(value, dict)
                    or set(value) != {"enabled", "selectors"}
                    or type(value["enabled"]) is not bool
                    or not isinstance(value["selectors"], dict)
                    or set(value["selectors"]) != set(FIELDS)
                ):
                    raise ValueError("Choose browser enablement and every selector")
                for v in value["selectors"].values():
                    text(v, 200)
                store.remember(profile, "kitchen.browser", value)
            return preference(
                store,
                profile,
                "kitchen.browser",
                {"enabled": False, "selectors": {k: "" for k in FIELDS}},
            )

    @contextmanager
    def page(self, login=False):
        from playwright.sync_api import sync_playwright

        folder = self.folder / "kitchen-browser"
        folder.mkdir(mode=0o700, exist_ok=True)
        if folder.is_symlink() or folder.stat().st_mode & 0o077:
            raise PermissionError("Browser profile must be private")
        with sync_playwright() as p:
            browser = p.chromium.launch_persistent_context(
                str(folder), headless=not login, accept_downloads=False
            )
            try:
                page = browser.pages[0] if browser.pages else browser.new_page()
                page.set_default_timeout(10000)
                page.route(
                    "**/*",
                    lambda route: (
                        route.continue_()
                        if route.request.resource_type
                        in (
                            "document",
                            "script",
                            "stylesheet",
                            "xhr",
                            "fetch",
                            "image",
                            "font",
                            "other",
                        )
                        else route.abort()
                    ),
                )
                yield page
            finally:
                browser.close()

    @staticmethod
    def check(page):
        host = urlsplit(page.url).hostname or ""
        if host != "www.safeway.com" and host != "safeway.com":
            raise ValueError("Retailer navigation left Safeway")
        if re.search(r"sign.?in|log.?in|captcha|access denied", page.title(), re.I):
            raise ValueError("Retailer needs owner login or verification")

    def search(self, items):
        cfg = self.configure()
        if not cfg["enabled"]:
            raise PermissionError("Configure the private shopping browser first")
        fields = cfg["selectors"]
        products = []
        with self.page() as page:
            for item in items:
                page.goto(
                    "https://www.safeway.com/shop/search-results.html?q=" + quote(item["name"]),
                    wait_until="domcontentloaded",
                    timeout=30000,
                )
                self.check(page)
                if page.locator(fields["store"]).inner_text().strip() != fields["expected_store"]:
                    raise ValueError("Retailer store changed")
                cards = page.locator(fields["card"])
                cards.first.wait_for()
                matches = []
                for i in range(min(cards.count(), 10)):
                    card = cards.nth(i)
                    name = card.locator(fields["name"]).inner_text()
                    # No inferred package/weight conversions or model-chosen substitutions.
                    if item["name"].casefold() not in name.casefold():
                        continue
                    identity = card.get_attribute(fields["product_id_attribute"])
                    if not identity:
                        continue
                    matches.append(
                        dict(
                            product_id=text(identity, 80),
                            name=text(name),
                            price_cents=money(card.locator(fields["price"]).inner_text()),
                            packs=1,
                            requested_name=item["name"],
                        )
                    )
                if not matches:
                    raise ValueError("No exact candidate; owner must review substitutions")
                products.append(min(matches, key=lambda v: v["price_cents"]))
        return products

    def add_exact(self, product):
        cfg = self.configure()
        if not cfg["enabled"]:
            raise PermissionError("Shopping browser disabled")
        f = cfg["selectors"]
        with self.page() as page:
            page.goto(
                "https://www.safeway.com/shop/search-results.html?q=" + quote(product["name"]),
                wait_until="domcontentloaded",
                timeout=30000,
            )
            self.check(page)
            if page.locator(f["store"]).inner_text().strip() != f["expected_store"]:
                raise ValueError("Retailer store changed")
            cards = page.locator(f["card"])
            cards.first.wait_for()
            matches = [
                cards.nth(i)
                for i in range(cards.count())
                if cards.nth(i).get_attribute(f["product_id_attribute"]) == product["product_id"]
            ]
            if (
                len(matches) != 1
                or money(matches[0].locator(f["price"]).inner_text()) != product["price_cents"]
            ):
                raise ValueError("Exact reviewed product/price changed")
            before = int(page.locator(f["cart_count"]).inner_text())
            from playwright.sync_api import expect

            for count in range(product["packs"]):
                if money(matches[0].locator(f["price"]).inner_text()) != product["price_cents"]:
                    raise ValueError("Price changed during cart preparation")
                matches[0].locator(f["add"]).click()
                expect(page.locator(f["cart_count"])).to_have_text(str(before + count + 1))
            # Every pack requires an observable cart delta, not a click return alone.


def main():
    import argparse
    from .config import state_dir
    from .kitchen_shopping import Shopping

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", action="store_true")
    args = parser.parse_args()
    folder = state_dir() / "amadeus"
    adapter = Browser(folder)
    if args.login:
        with adapter.page(login=True) as page:
            page.goto("https://www.safeway.com/")
            input(
                "Sign in and select your store/pickup preferences privately, then press Enter here: "
            )
    else:
        result = Shopping(folder).run(adapter)
        print({"state": result.get("status", result.get("state"))})


if __name__ == "__main__":
    main()
