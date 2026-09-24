#!/usr/bin/env python3
"""Convert Baby Stav's public Google RSS feed to an OpenAI Ads product CSV."""
import csv
import html
import io
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

SOURCE = "https://www.babystav.co.il/pages_google_feed"
OUTPUT = Path("docs/products.csv")
FIELDS = ("item_id", "title", "description", "url", "brand", "seller_name",
          "image_url", "availability", "price", "sale_price", "is_ads_eligible")
G = "{http://base.google.com/ns/1.0}"
STOCK = {"in stock": "in_stock", "out of stock": "out_of_stock",
         "preorder": "pre_order", "pre-order": "pre_order",
         "backorder": "backorder", "in_stock": "in_stock",
         "out_of_stock": "out_of_stock"}


def clean(value):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value or ""))).strip()


def money(value):
    amount, currency = clean(value).split()
    number = Decimal(amount)
    if number <= 0 or currency != "ILS" or not number.is_finite():
        raise ValueError("invalid price or currency")
    return f"{number:.2f} ILS"


def valid_url(value):
    parts = urlsplit(value)
    return parts.scheme == "https" and bool(parts.netloc) and not parts.username and not parts.password


def convert(data):
    root = ET.fromstring(data)
    items = root.findall("./channel/item")
    if len(items) < 500:
        raise ValueError(f"Suspiciously small source feed: {len(items)} items")
    rows, seen, errors = [], set(), []
    for index, item in enumerate(items, 1):
        get = lambda key: clean(item.findtext(G + key))
        try:
            regular = money(get("price"))
            sale = get("sale_price")
            if sale:
                sale = money(sale)
                if Decimal(sale.split()[0]) >= Decimal(regular.split()[0]):
                    sale = ""
            row = dict(item_id=get("id"), title=get("title")[:150],
                       description=get("description")[:5000], url=get("link"),
                       brand=get("brand"), seller_name="בייבי סתיו",
                       image_url=get("image_link"),
                       availability=STOCK[get("availability").lower()],
                       price=regular, sale_price=sale, is_ads_eligible="true")
            if not all(row[k] for k in ("item_id", "title", "description", "url", "brand", "image_url")):
                raise ValueError("missing required field")
            if not valid_url(row["url"]) or not valid_url(row["image_url"]):
                raise ValueError("invalid HTTPS URL")
            if row["item_id"] in seen:
                raise ValueError("duplicate item_id")
            seen.add(row["item_id"])
            rows.append(row)
        except (ValueError, KeyError, InvalidOperation) as exc:
            errors.append(f"item {index}: {exc}")
    if len(rows) < len(items) * .95:
        raise ValueError(f"Too many invalid products: {len(rows)}/{len(items)}. Sample: {errors[:5]}")
    print(f"Source: {len(items)}; exported: {len(rows)}; skipped: {len(errors)}")
    if errors:
        print("Skipped samples:", errors[:5], file=sys.stderr)
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def main():
    request = urllib.request.Request(SOURCE, headers={"User-Agent": "Mozilla/5.0 BabyStavFeedUpdater/1.0"})
    with urllib.request.urlopen(request, timeout=90) as response:
        data = response.read(20_000_001)
    if len(data) > 20_000_000:
        raise ValueError("Feed exceeds 20 MB")
    csv_data = convert(data)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(csv_data, encoding="utf-8", newline="")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
