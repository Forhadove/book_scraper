# 📚 E-Commerce Intelligence Web Scraper

> A production-grade, fault-tolerant Python web scraper designed to extract deep product metadata across multiple catalog and detail pages with dynamic DOM pagination, exponential backoff retries, and checkpoint-based crash recovery.

---

## 🎯 Project Overview & Objective

This project was built to meet the requirements of an e-commerce intelligence pipeline targeting **[Books to Scrape](http://books.toscrape.com/)**. It adheres strictly to modern data engineering practices:

- **No Hardcoded Page URLs**: Dynamically discovers and traverses pages by inspecting the DOM for the `<li class="next"><a href="...">` element.
- **Two-Stage (Master-Detail) Architecture**: Discovers product links on catalog pages, then visits each detail page individually to extract complete, non-truncated metadata.
- **100 Unique Products**: Crawls exactly 5 consecutive catalog pages (20 books/page = 100 books).
- **Fault-Tolerant & Checkpoint-Enabled**: Saves progress to `data/scraper_state.json`. If terminated mid-run (network failure or `Ctrl+C`), it resumes seamlessly without duplicating records.
- **Deterministic Deduplication**: Uses a 16-character SHA-256 hash of the canonical URL (`item_id`) to ensure idempotency.
- **Bonus Feature**: Automatically identifies the top 10 highest-rated books, downloads their high-resolution cover images into `media/`, and links the local path in CSV/JSON outputs.

---

## 📁 Repository Structure

```
book_scraper/
│
├── core/
│   ├── __init__.py           # Package exports
│   ├── config.py             # HTTP headers, delays, retries, file paths
│   ├── parser.py             # BeautifulSoup DOM parsing, sanitizers, schema validation
│   ├── checkpoint.py         # scraper_state.json state tracking & atomic saving
│   ├── storage.py            # CSV/JSON export & console analytics summary
│   └── scraper.py            # Main engine: dynamic pagination, retries, master-detail
│
├── data/
│   ├── books.csv             # Sanitized CSV output dataset
│   ├── books.json            # Pretty-printed JSON output dataset
│   └── scraper_state.json    # Checkpoint recovery file
│
├── media/                    # Downloaded .jpg cover images for top 10 rated books
│
├── main.py                   # CLI entry point with flags (--reset, --pages, --items)
├── requirements.txt          # Python dependencies
├── .gitignore                # Git ignore rules
└── README.md                 # Complete documentation & viva guide
```

---

## 🛠️ Extracted Fields & Data Schema

Each product record contains the following sanitized fields:

| Field Name | Type | Description | Extraction Strategy |
| :--- | :--- | :--- | :--- |
| `item_id` | `str` | Deterministic 16-char SHA-256 hash | `hashlib.sha256(url.encode()).hexdigest()[:16]` |
| `full_title` | `str` | Complete book title | Extracted from `<h1>` on the product page |
| `upc` | `str` | Unique Product Code | Parsed from the product specification table |
| `category` | `str` | Product category | Extracted from the 3rd breadcrumb element |
| `price_gbp` | `float` | Price in British Pounds (£) | Cleaned numeric float (e.g., `51.77`) |
| `rating_stars`| `int` | Rating score (1 to 5) | Parsed from CSS classes (`One` through `Five`) |
| `stock_quantity` | `int` | Exact available stock | Parsed via regex from `"In stock (X available)"` |
| `in_stock` | `bool` | Stock availability boolean | `True` if `stock_quantity > 0` |
| `source_url` | `str` | Canonical product detail URL | Resolved absolute URL |
| `cover_image_url` | `str` | Remote image URL | Resolved absolute URL from carousel/gallery |
| `local_image_path` | `str` | Local image file path | Linked for top 10 rated books (e.g., `media/<id>.jpg`) |

---

## ⚙️ Core Technical Highlights

### 1. Dynamic DOM Pagination (No Hardcoding)
Rather than constructing `page-1.html`, `page-2.html`, etc., the scraper inspects the catalog DOM:
```python
next_link = soup.select_one("li.next a")
if next_link and next_link.get("href"):
    next_page_url = urljoin(current_page_url, next_link.get("href"))
```
Relative paths (e.g., `catalogue/page-2.html` on the homepage vs `page-3.html` on page 2) are automatically resolved using Python's `urllib.parse.urljoin`.

### 2. Two-Stage Master-Detail Crawling
- **Stage 1 (Master)**: Gathers book links from the catalog cards.
- **Stage 2 (Detail)**: Navigates to each book's individual page to retrieve fields absent or truncated on the catalog card: full untruncated title, UPC, category breadcrumb, and exact inventory count.

### 3. Exponential Backoff Retry Policy
Network requests are wrapped with a resilient retry loop:
- **Handled Exceptions**: `requests.exceptions.RequestException`, timeouts, HTTP 429 (Too Many Requests), and 5xx (500, 502, 503, 504).
- **Backoff Formula**:
  $$\text{Wait Time} = \text{BACKOFF\_FACTOR} \times 2^{\text{attempt} - 1} + \text{jitter}$$
- Maximum retries: 3 attempts before graceful failure logging.

### 4. Checkpoint-Enabled Crash Recovery
Progress is persisted in `data/scraper_state.json`:
```json
{
  "completed_pages": ["http://books.toscrape.com/"],
  "current_page_url": "http://books.toscrape.com/catalogue/page-2.html",
  "scraped_item_ids": ["a48bc5eb48da3006", "bc2d423120d4d2cb"],
  "pages_processed_count": 1,
  "last_updated": "2026-11-15T18:30:10.123456"
}
```
If interrupted (e.g., via `Ctrl+C` or a network drop):
1. On relaunch, the scraper reads `scraper_state.json`.
2. Pages in `completed_pages` and items in `scraped_item_ids` are skipped without issuing redundant HTTP requests.
3. Scraping resumes seamlessly from the exact page where it left off.

### 5. Politeness & Anti-Bot Compliance
- Randomized jitter delay between **1.0 and 2.5 seconds** per request.
- Realistic HTTP headers (`User-Agent`, `Accept-Language`, and dynamic `Referer`).

---

## 🚀 Installation & Running Guide

### Step 1: Clone or Navigate to the Repository
```bash
cd book_scraper
```

### Step 2: Create and Activate Virtual Environment
**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Required Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Run the Scraper
```bash
python main.py
```

### CLI Command Options:
- **Fresh Run (Reset Checkpoint)**:
  ```bash
  python main.py --reset
  ```
- **Custom Page / Item Target**:
  ```bash
  python main.py --pages 5 --items 100
  ```
- **Verbose Debug Logging**:
  ```bash
  python main.py --verbose
  ```

---

## 🧪 Testing Checkpoint Recovery (Demo Walkthrough)

To verify the checkpoint recovery mechanism for your submission screenshots:

1. **Start a fresh run and interrupt it:**
   ```bash
   python main.py --reset
   ```
   *Press `Ctrl+C` in your terminal after 10–15 books have been scraped.*
2. **Inspect the generated checkpoint:**
   Open `data/scraper_state.json` to verify that `scraped_item_ids` and `current_page_url` are preserved.
3. **Resume the scraper:**
   ```bash
   python main.py
   ```
   *Notice the console log outputs:*
   ```text
   [INFO] Checkpoint resumed: X items previously scraped.
   [INFO] ⏭️ Skipping already scraped item (xyz) without network call.
   ```
   The scraper picks up where it stopped and completes the remaining items without duplicate records!

---

## 🎓 Viva / Defense Preparation Guide

Be prepared to answer these core technical questions:

### Q1: Why is hardcoding pagination (`page-{i}.html`) prohibited in real-world scraping?
> **Answer**: Real websites frequently change URL structures, filter order, or implement cursor-based / token-based pagination (e.g., `?after=cursor_id`). Relying on hardcoded index numbers makes scrapers fragile. Inspecting the DOM for `<li class="next"><a href="...">` and resolving relative URLs via `urljoin` reflects how humans navigate, adapting automatically if the site structure changes.

### Q2: How does the Two-Stage (Master-Detail) pattern benefit data quality?
> **Answer**: Catalog pages only show preview snippets; for example, long book titles are truncated with ellipses (`...`), exact warehouse inventory numbers are omitted, and UPC codes are not present. By using a two-stage approach, Stage 1 gathers valid entry points, while Stage 2 visits the canonical detail page to extract complete, non-truncated fields.

### Q3: How does the deterministic `item_id` hash prevent duplicates?
> **Answer**: We compute `hashlib.sha256(canonical_url.encode('utf-8')).hexdigest()[:16]`. Because SHA-256 is a deterministic cryptographic hash, identical URLs always yield the exact same 16-character hex identifier. When merging resumed runs, storing items in an associative key-value map keyed by `item_id` guarantees idempotency and zero duplicates.

### Q4: Explain the exponential backoff algorithm with jitter.
> **Answer**: If a server experiences rate limiting (HTTP 429) or temporary server load (500/502/503/504), hammering it with immediate retries exacerbates the congestion. Exponential backoff progressively doubles the wait time between retries ($1.5 \times 2^{\text{attempt}-1}$). Adding random jitter prevents the "thundering herd" problem where multiple client requests retry simultaneously at identical intervals.

---

## 📄 License
This project is open-source and intended for academic practice and educational evaluation.
