# Pantry and grocery preparation — proposed next phase

Status: researched design, not an enabled adapter or inventory collector. Start with
user-shared receipts and short barcode intake sessions, then use camera sightings
to reconcile that evidence. Keep shopping preparation separate from inventory and
require a distinct approval before any external retailer write.

## Intake and realistic limits

- Safeway supports purchase history in its [consumer app](https://www.safeway.com/about-us/mobile-apps.html).
  No supported public receipt/cart API was verified. Begin with shared receipt
  images/PDFs; do not scrape account cookies or imply direct cart access.
- A barcode identifies a product, not the amount left or usually its expiry.
  [GS1 2D formats](https://ref.gs1.org/guidelines/2d-in-retail/) can carry dates/lot
  data when actually encoded. Printed dates remain separate observed fields.
- [Home Assistant tags](https://www.home-assistant.io/integrations/tag/) can start
  a bounded put-away scan, mark an item used up, or add it to a local shopping draft.
  Dashboard mappings own actions; tags contain only opaque IDs.
- Android [barcode scanning](https://developers.google.com/ml-kit/vision/barcode-scanning/android)
  and [OCR](https://developers.google.com/ml-kit/vision/text-recognition/v2/android)
  can run on-device. ML Kit still has usage/performance telemetry under its
  [terms](https://developers.google.com/ml-kit/terms); use ZXing/Tesseract when
  stricter local-only processing is required. Optional cached
  [Open Food Facts](https://github.com/openfoodfacts/openfoodfacts-server/blob/main/docs/api/index.md)
  lookups are incomplete product metadata, not household stock.
- A fixed camera sees packaging and occlusion, not reliable consumption. Start
  with intentional phone sessions; run ambiguous-image analysis on the Mac on
  demand, with memory/latency checks alongside conversation and speech workers.

## Private evidence and inventory model

An observation has a stable provider ID, observed/ingested times, session ID,
evidence hash/reference, proposed fields, per-field confidence, parser version and
review state. Products have optional GTIN/retailer SKU and package size. Lots
represent particular purchase batches and storage locations. Append idempotent
receive/open/consume/transfer/discard/correction movements with operation IDs,
revisions and owner decisions; keep corrections undoable.

A receipt and a camera sighting of the same purchase must reconcile, not add twice.
Repeated frames/tag retries must be idempotent. Different purchases of the same
barcode remain different lots. A receipt proves purchase evidence, not delivery or
put-away. Model confidence is not a calibrated probability. Track confirmed,
probable, needs-check, unknown and explicitly out-of-stock states; missing/stale
images never prove zero stock. Begin with packs/counts and known units. Keep
observed dates separate from estimated reminders; do not infer food safety.

The largest signal gap is consumption: provide quick used-up/opened/cooked actions
and occasional reconciliation. A recipe suggestion does not consume ingredients.

## Incremental delivery

1. Private ledger, review/undo, dashboard storage locations and NFC mapping. Reuse
   leased character work stages without disclosing ingredient contents to displays.
2. Android share intake, receipt parsing, barcode/OCR session matching and batch
   approval. Validate representative private receipts and a short put-away scan.
3. Grounded stock/uncertainty/preference/recipe tools and structured shopping drafts.
   Current temporary string-list drafts are not a durable pantry database.
4. An approved provider handoff, then optional fixed-camera sessions. Bind approval
   to content/provider/operation/revision, expire it and reconcile ambiguous failures.

[Instacart shopping-list pages](https://docs.instacart.com/developer_platform_api/api/products/create_shopping_list_page/)
are a possible handoff: users choose a store and checkout themselves. Its
[FAQ](https://docs.instacart.com/developer_platform_api/faq/) does not guarantee a
fixed merchant or exact quantities. Verify developer access, local pickup availability
and pricing before adopting it; do not promise a Safeway-specific cart.
[Grocy](https://grocy.info/) is an optional authoritative inventory adapter later;
avoid maintaining two writable stock totals. Existing recipe feeds can remain recipe
sources without claiming inventory ownership.

## Onboarding and privacy

Independently opt into receipts, camera intake, external product lookup, pantry
memory and grocery handoff. Configure storage locations, NFC actions, capture length,
review thresholds, retention and deletion/export in the dashboard. Start inputs off.
Crop/redact receipts, retain raw images briefly, and give normalized inventory its
own lifecycle. Treat OCR as untrusted input; never infer health goals/preferences
from purchases. Use invented fixtures in the public repository; keep actual receipts,
images, inventory and evaluations in ignored private state. A fixed-camera trial,
representative receipts and retailer permissions require owner participation later.
