"""
Data storage and analytics summary module.
Handles reading and writing to CSV and JSON formats, and computes analytical metrics.
"""
import csv
import json
import logging
from pathlib import Path
from typing import Dict, List

from .config import CSV_FILE_PATH, JSON_FILE_PATH

logger = logging.getLogger(__name__)

CSV_FIELDNAMES = [
    "item_id",
    "full_title",
    "upc",
    "category",
    "price_gbp",
    "rating_stars",
    "stock_quantity",
    "in_stock",
    "source_url",
    "cover_image_url",
    "local_image_path",
]


def load_existing_records(json_path: Path = JSON_FILE_PATH) -> Dict[str, Dict]:
    """
    Loads existing records from the JSON file to prevent duplication across runs.
    Returns a dictionary mapping item_id -> record.
    """
    if not json_path.exists():
        return {}

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            records = json.load(f)
            return {r["item_id"]: r for r in records if "item_id" in r}
    except Exception as e:
        logger.warning(f"Could not load existing records from {json_path}: {e}")
        return {}


def save_records(
    records: List[Dict],
    csv_path: Path = CSV_FILE_PATH,
    json_path: Path = JSON_FILE_PATH,
) -> None:
    """
    Saves the list of records to both CSV and JSON formats.
    """
    # 1. Save to JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(records)} records to {json_path}")

    # 2. Save to CSV
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r)
    logger.info(f"Saved {len(records)} records to {csv_path}")


def compute_analytics_summary(records: List[Dict]) -> Dict:
    """
    Computes analytical metrics across scraped product records:
    - Total records
    - Average book price
    - Category breakdown
    - Cheapest and most expensive books
    - Rating breakdown
    """
    if not records:
        return {
            "total_records": 0,
            "avg_price": 0.0,
            "categories": {},
            "cheapest_book": None,
            "most_expensive_book": None,
            "rating_distribution": {},
        }

    total_records = len(records)
    total_price = sum(r["price_gbp"] for r in records)
    avg_price = total_price / total_records if total_records > 0 else 0.0

    # Category counts
    category_counts: Dict[str, int] = {}
    rating_counts: Dict[int, int] = {}

    for r in records:
        cat = r.get("category", "Unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1

        rating = r.get("rating_stars", 0)
        rating_counts[rating] = rating_counts.get(rating, 0) + 1

    # Sorted categories by count descending
    sorted_categories = dict(sorted(category_counts.items(), key=lambda item: item[1], reverse=True))
    sorted_ratings = dict(sorted(rating_counts.items(), key=lambda item: item[0], reverse=True))

    cheapest_book = min(records, key=lambda r: r["price_gbp"])
    most_expensive_book = max(records, key=lambda r: r["price_gbp"])

    return {
        "total_records": total_records,
        "avg_price": round(avg_price, 2),
        "categories": sorted_categories,
        "cheapest_book": {
            "title": cheapest_book["full_title"],
            "price_gbp": cheapest_book["price_gbp"],
            "url": cheapest_book["source_url"],
        },
        "most_expensive_book": {
            "title": most_expensive_book["full_title"],
            "price_gbp": most_expensive_book["price_gbp"],
            "url": most_expensive_book["source_url"],
        },
        "rating_distribution": sorted_ratings,
    }


def print_console_summary(summary: Dict) -> None:
    """
    Prints a formatted, professional dashboard report to the console.
    """
    divider = "=" * 70
    sub_divider = "-" * 70

    print("\n" + divider)
    print("   📊 E-COMMERCE INTELLIGENCE SCRAPER: FINAL DATASET SUMMARY")
    print(divider)

    print(f"  • Total Unique Records Scraped : {summary['total_records']}")
    print(f"  • Average Product Price        : £{summary['avg_price']:.2f}")

    cheapest = summary.get("cheapest_book")
    if cheapest:
        print(f"\n  📉 Cheapest Book:")
        print(f"     - Title : {cheapest['title']}")
        print(f"     - Price : £{cheapest['price_gbp']:.2f}")
        print(f"     - Link  : {cheapest['url']}")

    expensive = summary.get("most_expensive_book")
    if expensive:
        print(f"\n  📈 Most Expensive Book:")
        print(f"     - Title : {expensive['title']}")
        print(f"     - Price : £{expensive['price_gbp']:.2f}")
        print(f"     - Link  : {expensive['url']}")

    print(f"\n{sub_divider}")
    print("  📚 Category Breakdown:")
    for cat, count in summary.get("categories", {}).items():
        bar = "█" * min(25, count * 2)
        print(f"     {cat:<22} : {count:>3} items  {bar}")

    print(f"\n{sub_divider}")
    print("  ⭐ Rating Star Distribution:")
    for star, count in summary.get("rating_distribution", {}).items():
        star_str = "★" * star + "☆" * (5 - star)
        print(f"     {star_str} ({star} stars) : {count:>3} items")

    print(divider + "\n")
