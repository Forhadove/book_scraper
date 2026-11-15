"""
HTML parsing and record sanitization module.
Extracts catalog links, parses detailed product metadata, generates deterministic hashes,
and validates records against the schema.
"""
import hashlib
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin
from bs4 import BeautifulSoup

# Star class to integer map
STAR_RATING_MAP = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
}


def generate_item_id(canonical_url: str) -> str:
    """
    Generate a deterministic 16-character SHA-256 hash of the product URL.
    Ensures idempotency and deduplication across multiple runs.
    """
    cleaned_url = canonical_url.strip().lower()
    return hashlib.sha256(cleaned_url.encode("utf-8")).hexdigest()[:16]


def parse_catalog_page(html_content: str, current_page_url: str) -> Tuple[List[str], Optional[str]]:
    """
    Parses a catalog page to find:
    1. Product detail URLs for all book pods.
    2. The 'next' page URL dynamically from the DOM (never hardcoded).
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Extract book detail page URLs
    detail_urls: List[str] = []
    product_pods = soup.select("article.product_pod h3 a")
    for link in product_pods:
        href = link.get("href")
        if href:
            absolute_url = urljoin(current_page_url, href)
            detail_urls.append(absolute_url)

    # 2. Extract next page link dynamically
    next_link = soup.select_one("li.next a")
    next_page_url = None
    if next_link and next_link.get("href"):
        next_page_url = urljoin(current_page_url, next_link.get("href"))

    return detail_urls, next_page_url


def parse_product_detail_page(html_content: str, product_url: str) -> Dict:
    """
    Parses a single product's detail page and returns sanitized metadata fields.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Full Title (from <h1>, avoids ellipsis truncation from catalog cards)
    h1_tag = soup.find("h1")
    full_title = h1_tag.get_text(strip=True) if h1_tag else ""

    # 2. Extract table fields (UPC, Price, Availability)
    product_table = {}
    for row in soup.select("table.table-striped tr"):
        th = row.find("th")
        td = row.find("td")
        if th and td:
            key = th.get_text(strip=True).lower()
            product_table[key] = td.get_text(strip=True)

    upc = product_table.get("upc", "")

    # 3. Category from Breadcrumb: Home > Books > [Category] > Book Title
    category = "General"
    breadcrumb_links = soup.select("ul.breadcrumb li a")
    if len(breadcrumb_links) >= 3:
        category = breadcrumb_links[2].get_text(strip=True)
    elif len(breadcrumb_links) >= 2:
        category = breadcrumb_links[1].get_text(strip=True)

    # 4. Clean Price GBP
    price_raw = product_table.get("price (incl. tax)", "")
    if not price_raw:
        price_tag = soup.select_one("p.price_color")
        price_raw = price_tag.get_text(strip=True) if price_tag else "0.0"

    price_match = re.search(r"(\d+(?:\.\d+)?)", price_raw)
    price_gbp = float(price_match.group(1)) if price_match else 0.0

    # 5. Rating Stars (1-5)
    rating_stars = 0
    star_tag = soup.select_one("p.star-rating")
    if star_tag:
        classes = star_tag.get("class", [])
        for c in classes:
            lowered = c.lower()
            if lowered in STAR_RATING_MAP:
                rating_stars = STAR_RATING_MAP[lowered]
                break

    # 6. Stock Quantity & In Stock Status
    # Format e.g.: "In stock (22 available)"
    avail_text = product_table.get("availability", "")
    if not avail_text:
        avail_tag = soup.select_one(".availability")
        avail_text = avail_tag.get_text(strip=True) if avail_tag else ""

    stock_match = re.search(r"\((\d+)\s+available\)", avail_text)
    if stock_match:
        stock_quantity = int(stock_match.group(1))
    elif "in stock" in avail_text.lower():
        stock_quantity = 1
    else:
        stock_quantity = 0

    in_stock = stock_quantity > 0

    # 7. Image Cover URL
    img_tag = soup.select_one("div.carousel-inner div.item.active img, #product_gallery img")
    cover_image_url = ""
    if img_tag and img_tag.get("src"):
        cover_image_url = urljoin(product_url, img_tag.get("src"))

    # 8. Deterministic Item ID
    item_id = generate_item_id(product_url)

    return {
        "item_id": item_id,
        "full_title": full_title,
        "upc": upc,
        "category": category,
        "price_gbp": price_gbp,
        "rating_stars": rating_stars,
        "stock_quantity": stock_quantity,
        "in_stock": in_stock,
        "source_url": product_url,
        "cover_image_url": cover_image_url,
        "local_image_path": ""  # populated in bonus stage for top 10 rated
    }


def validate_record(record: Dict) -> Tuple[bool, str]:
    """
    Validates a scraped product record against the required schema.
    Returns (is_valid, error_message).
    """
    required_keys = [
        "item_id", "full_title", "upc", "category",
        "price_gbp", "rating_stars", "stock_quantity",
        "in_stock", "source_url"
    ]

    for key in required_keys:
        if key not in record:
            return False, f"Missing required key: {key}"

    if not isinstance(record["item_id"], str) or len(record["item_id"]) != 16:
        return False, f"Invalid item_id format: {record.get('item_id')}"

    if not isinstance(record["full_title"], str) or not record["full_title"].strip():
        return False, "full_title must be a non-empty string"

    if not isinstance(record["upc"], str) or not record["upc"].strip():
        return False, "upc must be a non-empty string"

    if not isinstance(record["price_gbp"], (int, float)) or record["price_gbp"] < 0:
        return False, f"price_gbp must be a non-negative number: {record.get('price_gbp')}"

    if not isinstance(record["rating_stars"], int) or not (1 <= record["rating_stars"] <= 5):
        return False, f"rating_stars must be an integer between 1 and 5: {record.get('rating_stars')}"

    if not isinstance(record["stock_quantity"], int) or record["stock_quantity"] < 0:
        return False, f"stock_quantity must be a non-negative integer: {record.get('stock_quantity')}"

    if not isinstance(record["in_stock"], bool):
        return False, f"in_stock must be a boolean: {record.get('in_stock')}"

    if not isinstance(record["source_url"], str) or not record["source_url"].startswith("http"):
        return False, f"Invalid source_url: {record.get('source_url')}"

    return True, "Valid"
