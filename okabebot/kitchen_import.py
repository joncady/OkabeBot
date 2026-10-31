"""Untrusted import normalization; nothing here writes inventory or keeps raw images."""

import base64
import csv
from io import StringIO
import json
from pathlib import Path
import re
import subprocess
import sys
import shutil
import tempfile

from .kitchen import text


def parse(raw, format="text", long_lasting=False):
    if not isinstance(raw, str) or not 0 < len(raw.encode()) <= 500000:
        raise ValueError("Use a receipt/export within 500 KB")
    if format == "json":
        value = json.loads(raw)
        rows = value.get("items", value.get("stock", [])) if isinstance(value, dict) else value
        if not isinstance(rows, list):
            raise ValueError("Use a JSON ingredient array or items/stock export")
        items = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Use structured ingredient rows")
            product = row.get("product") or {}
            if not isinstance(product, dict):
                product = {}
            location = row.get("location", "pantry")
            if isinstance(location, dict):
                location = location.get("name", "pantry")
            items.append(
                dict(
                    name=row.get("name", product.get("name")),
                    quantity=float(row.get("quantity", row.get("amount", 1))),
                    unit=row.get("unit", "count"),
                    location=location,
                    best_by=row.get("best_by", row.get("best_before_date")),
                    long_lasting=long_lasting,
                    confidence="needs_check",
                )
            )
        return items
    if format == "csv":
        return parse(json.dumps(list(csv.DictReader(StringIO(raw)))), "json", long_lasting)
    if format not in ("text", "receipt"):
        raise ValueError("Choose text, receipt, CSV or JSON")
    items = []
    for line in raw.splitlines():
        value = line.strip()
        if not value:
            continue
        if format == "receipt":
            if re.search(
                r"\b(total|subtotal|tax|change|visa|mastercard|balance|savings|payment|coupon|cashier|loyalty)\b",
                value,
                re.I,
            ):
                continue
            # A price-bearing line is only a candidate, never evidence of food or quantity.
            match = re.match(r"(.+?)\s+\$?\d+[.,]\d{2}\s*[A-Z]?$", value)
            if not match:
                continue
            value = match[1].strip()
        quantity, unit = 1, "count"
        match = re.match(
            r"^(\d+(?:\.\d+)?)\s*(kg|g|ml|l|lb|oz|count|pack|can|bottle|bag)?\s+(.*)$", value, re.I
        )
        if match:
            quantity = float(match[1])
            unit = (match[2] or "count").casefold()
            value = match[3]
        items.append(
            dict(
                name=text(value),
                quantity=quantity,
                unit=unit,
                location="pantry",
                long_lasting=long_lasting,
                confidence="needs_check",
            )
        )
    if not items:
        raise ValueError(
            "No ingredient candidates found. Copy item lines or use CSV; no stock was changed"
        )
    return items


def ocr_image(encoded):
    if not isinstance(encoded, str) or len(encoded) > 12_000_000:
        raise ValueError("Use a receipt photo smaller than 8 MB")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        raise ValueError("Invalid receipt image") from None
    if len(raw) > 8_000_000:
        raise ValueError("Use a receipt photo smaller than 8 MB")
    # Validate image format/pixel count before invoking native code; no persistent raw receipt.
    from PIL import Image
    from io import BytesIO

    with Image.open(BytesIO(raw)) as image:
        if image.width * image.height > 30_000_000 or image.format not in ("JPEG", "PNG", "WEBP"):
            raise ValueError("Use a JPEG/PNG/WebP receipt image below 30 megapixels")
        with tempfile.TemporaryDirectory(prefix="amadeus-receipt-") as folder:
            image.convert("RGB").save(Path(folder) / "receipt.png")
            executable = shutil.which("tesseract")
            if not executable:
                executable = next(
                    (
                        str(p)
                        for p in (
                            Path("/opt/homebrew/bin/tesseract"),
                            Path("/usr/local/bin/tesseract"),
                        )
                        if p.is_file()
                    ),
                    None,
                )
            if executable:
                result = subprocess.run(
                    [executable, str(Path(folder) / "receipt.png"), "stdout", "--psm", "6"],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode == 0:
                    return result.stdout[:500000]
            if sys.platform != "darwin":
                raise ValueError("Install Tesseract for local image OCR, or paste receipt text")
            script = Path(__file__).parent / "assets/receipt-ocr.swift"
            result = subprocess.run(
                ["/usr/bin/swift", str(script), str(Path(folder) / "receipt.png")],
                capture_output=True,
                text=True,
                timeout=90,
            )
            if result.returncode:
                raise ValueError("Local OCR unavailable; paste receipt text instead")
            return result.stdout[:500000]
