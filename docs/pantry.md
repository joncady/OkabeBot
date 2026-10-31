# Kitchen helper

Status: implemented source, disabled until private setup; not an installed collector
or a verified live retailer connection. Inventory is owned by Amadeus, with imports
from other tools rather than a second writable stock database.

## Owner flow

Open **Dashboard → Kitchen helper**. Save private choices, then:

1. **Import pantry / grocery receipt**: paste staples one per line (`500 g rice`),
   upload CSV/JSON, paste digital receipt text, or select a physical receipt photo.
   Mark long-lasting staples explicitly. No expiry is guessed. The optional receipt
   ID can be the retailer's stable receipt/order ID; otherwise an evidence hash is
   generated. Use different IDs for different purchases.
2. Review candidate names, quantities, units, storage locations and observed dates.
   Uncheck non-food/OCR errors and confirm once. Repeating that confirmation is
   idempotent. Identical candidate sets on other IDs are flagged for reconciliation,
   not silently merged: two purchases can contain the same products.
3. **Confirmed ingredients** supports search, pagination, quantity verification and
   used-up correction. Observation age is explicit. Mass/volume units normalize
   within their dimension (kg/g, lb/oz, l/ml); there is no density or package-size
   conversion. Correct product names when imports use inconsistent aliases.
4. Add starter meal ideas or import structured Mealie recipe JSON; alternatively
   enter a recipe with known ingredient quantities/units. Starter ideas are not
   cooking instructions or food-safety guidance. Imported recipe ingredients need
   names, not only foreign database IDs.
5. **Meal plan & next shopping trip** prepares proposals and an aggregated missing-
   ingredient list. Inventory is reserved across proposed meals for planning only:
   recommending a meal does not consume stock. Nothing is ordered automatically.
6. **Kitchen NFC actions** learns a tag and maps it to a confirmed product: either
   mark that ingredient used up or add a configured amount/unit to a local shopping
   draft. Only real fresh HA scans execute; retries are deduplicated. Tag mappings
   contain opaque product IDs, not credentials. Existing room/chore actions remain.

Weekdays default to breakfast/dinner; weekends include lunch. Every choice is
editable: meal slots, planning horizon, meal hours/advance window, local indexing hour, freshness/date windows,
explicit tastes/avoidances, kitchen goals, eating-out choices and snooze. Saved food
preferences are also considered. Optional coaching uses explicit tags/goals, with
existing coaching consent required for additional saved meal goals; other-person
privacy suppresses coaching context. Exact avoid-tag matching is not an allergen
screen: verify recipes and product labels yourself.

The daily controller job runs once per local day after the configured hour, catches
up after controller restart and resumes an interrupted index. It does not scan the
physical kitchen or infer that an absent item is out of stock. Upcoming recorded
dates influence meal ranking. Past dates need checking and are excluded from
assumed usable ingredients. Date reminders and plans join existing proactive
attention gates (home, quiet, media, focus, budget, route), with factual revalidation
before speech; successful speech suppresses that meal slot and acknowledges date notes for the day,
without suppressing a later configured dinner suggestion.
Morning cards can also include the kitchen note. Kitchen snooze affects invitations,
not retention or quiet background planning. No automatic health inference is added.

## Local receipt OCR

Tesseract is the preferred local backend; install it on the controller (`brew install
tesseract` on macOS, or the distribution package on Linux). Images are validated,
converted in a private temporary directory and removed after extraction. Raw images
and receipt text are not stored. macOS Apple Vision is a fallback, but its native
inference can be unavailable on some environments; failures require pasted text or
Tesseract, never an automatic cloud upload. A development-machine native Vision
failure was bypassed with the local Tesseract backend and a synthetic receipt test.
OCR candidates still require review. Current intake supports JPEG/PNG/WebP, text,
CSV and JSON; for PDF receipts copy/export their text or a receipt image first.

[Google Lens](https://search.google/ways-to-search/lens/) can identify objects and
copy text manually. Pasted Lens text uses the same review path. It is not the
local image backend and may send images to Google. There is no verified supported
consumer Lens API wired here. Unlabeled produce recognition, live fridge cameras,
barcode capture and item-level reconciliation remain later work, not inferred stock.

## Optional Safeway preparation worker

Install the `kitchen` extra and Chromium, then sign in interactively with a dedicated
private browser profile:

```sh
python -m pip install -e '.[kitchen]'
python -m playwright install chromium
OKABEBOT_CONFIG=/path/to/private-config.json python -m okabebot.kitchen_browser --login
```

Select the store/fulfillment preferences privately. In **Safeway browser preparation**,
configure/verify the retailer's current product-card, name, price, product-ID, add/
increment, quantity-count and selected-store selectors plus expected store text.
This advanced contract deliberately has no guessed working defaults. The current
adapter requires a verifiable cart unit count, unambiguous prices and stable product
IDs. Login challenges, unsupported markup, missing matches or price/store changes
block the job rather than escalating privileges or guessing. Retailer selectors and
real account/cart behavior still require an owner-assisted acceptance test.

Enabling the browser allows daily drafts to queue product searches. Owners can also
queue a draft manually. The asynchronous worker prepares candidate matches; it does
not infer equivalent package sizes or substitutions. Review inclusion, package size,
price and pack count. Save changed product choices, then **Approve exact cart
additions**. That approval lasts fifteen minutes and binds product contents, draft
revision, provider/browser contract and kitchen settings. Changing any invalidates it.
Check missing items; the result may be partial. Do not edit the cart concurrently.

Cart additions verify an observable count delta for every pack. There is no checkout
operation in the worker interface. A crash/timeout after mutation is `unknown`, with
no automatic replay; inspect the cart manually. Cancellation stops future steps but
does not undo an already submitted change. The worker does not silently clear a cart,
select delivery times, pay, or claim an order was placed. Cart preparation is not a
purchase receipt or pantry intake.

A manual one-pass worker can run with `python -m okabebot.kitchen_browser`; normal
controller startup supplies its background coordinator. Its browser work publishes
leased content-free research/draft/review stages through the existing character
presentation interface. Browser sessions remain private account credentials; export
omits them. Sign out/remove the private browser profile separately when disconnecting
an account. Forgetting kitchen/Amadeus metadata disables further work and removes
normalized kitchen records/settings, but does not revoke an external retailer login.

## Storage, tools and adapters

Private `amadeus.sqlite3` owns subject-scoped products, lots, reviewed import evidence,
movements, recipes, plans, daily indexes and shopping jobs. Composite identity/name
indexes support paged ingredient lookup. Stable external IDs and transactional
operation receipts provide idempotency; revisions reject stale writes. Confirmed
imports discard candidate item copies; daily indexes retain references rather than
copying all stock. There is no passive consumption inference or raw-photo archive.
Owner export/delete and whole-profile forgetting include the kitchen tables.

Conversation exposes read-only `get_kitchen_ingredients`, `get_meal_suggestions`
and `get_kitchen_plan`. Tool replies use bounded selected facts; the initial prompt
contains routing guidance, not an entire pantry. Owner-only HTTP routes manage
inventory and cart approvals; paired phone credentials cannot grant approval.
Kitchen data remains subject to pause/guest controls. No new HA entity observation,
cloud OCR, cloud model or live retailer account is enabled by source installation.

[Grocy](https://grocy.info/) is a useful optional companion: it already tracks stock,
best-before dates, minimum quantities and recipe due scores. Its stock JSON with
embedded product names can be imported and corrected in the review table. Check
units from exports. A future authoritative Grocy adapter should replace Amadeus
stock ownership, not bidirectionally synchronize two writable totals.
[Mealie's API](https://mealie.io/documentation/getting-started/api-usage/) is suited
to recipes and shopping/meal plans; recipe JSON import works without storing another
token. Existing HA Mealie feeds remain separate, read-only context.

The local **conversation** Qwen model can select these typed tools; Qwen TTS is a
separate speech model and does not plan tasks. [Qwen-Agent](https://github.com/QwenLM/Qwen-Agent)
supports local model services and function calling, but a general autonomous visual
browser agent is not enabled here. This worker uses a constrained deterministic
browser adapter and explicit approval; learned product ranking or a richer agent
harness can be added behind that boundary after evaluation.

## Acceptance and later work

Synthetic ledger/HTTP/NFC/attention regressions, a complete isolated dashboard flow,
local receipt OCR and labeled tool-selection evaluations cover the source feature.
Live Safeway sign-in/selector/cart verification, representative private receipt and
Mealie/Grocy exports, taste/portion calibration and gentle-notification acceptance
remain owner checks. No source test is evidence that the installed controller has
this version. Live camera stock, semantic alias/unit reconciliation and a supported
retailer API/handoff remain follow-up capabilities in the backlog. No personal
receipts, inventory, preferences or trial outputs belong in public artifacts.
