"""
Configuration module for the E-Commerce Web Scraper.
Defines target URLs, request headers, rate limits, retry policies, and file paths.
"""
from pathlib import Path

# Base & Starting URL
BASE_URL = "http://books.toscrape.com/"
START_URL = "http://books.toscrape.com/"

# Scraping Limits
MAX_PAGES = 5
TARGET_ITEMS = 100
TOP_RATED_DOWNLOAD_COUNT = 10

# Politeness & Jitter Delay (in seconds)
MIN_DELAY = 1.0
MAX_DELAY = 2.5

# Exponential Backoff & Retry Parameters
MAX_RETRIES = 3
BACKOFF_FACTOR = 1.5  # sleep = BACKOFF_FACTOR * (2 ** (attempt - 1)) + jitter
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
REQUEST_TIMEOUT = 12  # seconds

# Realistic HTTP Headers
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "http://books.toscrape.com/",
    "Connection": "keep-alive",
}

# Project Directories & Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
MEDIA_DIR = PROJECT_ROOT / "media"

DATA_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

CSV_FILE_PATH = DATA_DIR / "books.csv"
JSON_FILE_PATH = DATA_DIR / "books.json"
CHECKPOINT_FILE_PATH = DATA_DIR / "scraper_state.json"
