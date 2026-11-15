"""
Core web scraper engine.
Implements:
1. Dynamic DOM pagination (following 'next' button href via urljoin).
2. Two-Stage Master-Detail architecture (Catalog -> Product Detail).
3. Exponential backoff retry logic for RequestException, timeouts, 429, 500, 502, 503, 504.
4. Randomized jitter sleep between requests.
5. Checkpoint-enabled resume functionality without duplicate records.
6. Schema validation and error logging without script termination.
7. Bonus: Top 10 highest-rated book cover image download into media folder.
"""
import logging
import random
import time
from pathlib import Path
from typing import Dict, List, Optional
import requests
from requests.exceptions import RequestException

from .checkpoint import CheckpointManager
from .config import (
    BACKOFF_FACTOR,
    DEFAULT_HEADERS,
    MAX_DELAY,
    MAX_PAGES,
    MAX_RETRIES,
    MEDIA_DIR,
    MIN_DELAY,
    REQUEST_TIMEOUT,
    RETRY_STATUS_CODES,
    START_URL,
    TARGET_ITEMS,
    TOP_RATED_DOWNLOAD_COUNT,
)
from .parser import (
    generate_item_id,
    parse_catalog_page,
    parse_product_detail_page,
    validate_record,
)
from .storage import (
    load_existing_records,
    save_records,
)

logger = logging.getLogger(__name__)


class EcommerceScraper:
    """
    Production-grade, fault-tolerant e-commerce scraper.
    """

    def __init__(
        self,
        start_url: str = START_URL,
        max_pages: int = MAX_PAGES,
        target_items: int = TARGET_ITEMS,
    ):
        self.start_url = start_url
        self.max_pages = max_pages
        self.target_items = target_items

        # Setup requests session with realistic headers
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

        # Checkpoint manager & existing records
        self.checkpoint = CheckpointManager()
        self.records_map: Dict[str, Dict] = load_existing_records()

        # Synchronize checkpoint with existing records
        for item_id in self.records_map.keys():
            self.checkpoint.register_item(item_id)

    def _sleep_jitter(self) -> None:
        """Applies randomized jitter delay between requests to respect rate limits."""
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        logger.debug(f"Jitter sleep for {delay:.2f} seconds...")
        time.sleep(delay)

    def fetch_url(self, url: str) -> Optional[str]:
        """
        Fetches an HTTP URL with exponential backoff retry logic.
        Handles RequestException, timeouts, 429 rate limits, and 5xx gateway errors.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Update Referer dynamically for realism
                self.session.headers["Referer"] = url

                response = self.session.get(url, timeout=REQUEST_TIMEOUT)

                # Check if retryable HTTP status code
                if response.status_code in RETRY_STATUS_CODES:
                    logger.warning(
                        f"[Attempt {attempt}/{MAX_RETRIES}] HTTP {response.status_code} on {url}."
                    )
                    if attempt < MAX_RETRIES:
                        backoff = BACKOFF_FACTOR * (2 ** (attempt - 1)) + random.uniform(0.5, 1.0)
                        logger.info(f"Retrying in {backoff:.2f}s due to status code {response.status_code}...")
                        time.sleep(backoff)
                        continue
                    else:
                        logger.error(f"Exhausted retries for {url} with status {response.status_code}.")
                        return None

                # Raise for any other 4xx/5xx errors
                response.raise_for_status()
                return response.text

            except RequestException as err:
                logger.warning(f"[Attempt {attempt}/{MAX_RETRIES}] Network exception on {url}: {err}")
                if attempt < MAX_RETRIES:
                    backoff = BACKOFF_FACTOR * (2 ** (attempt - 1)) + random.uniform(0.5, 1.0)
                    logger.info(f"Retrying in {backoff:.2f}s due to network error...")
                    time.sleep(backoff)
                else:
                    logger.error(f"Exhausted retries for {url}. Failed to retrieve.")
                    return None

        return None

    def download_image(self, image_url: str, item_id: str) -> Optional[str]:
        """
        Downloads a book cover image and saves it to media/{item_id}.jpg.
        Returns the relative local file path.
        """
        if not image_url:
            return None

        file_name = f"{item_id}.jpg"
        local_path = MEDIA_DIR / file_name

        # If already downloaded, return path
        if local_path.exists():
            return f"media/{file_name}"

        try:
            self._sleep_jitter()
            resp = self.session.get(image_url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"🖼️ Downloaded cover image to media/{file_name}")
                return f"media/{file_name}"
        except Exception as e:
            logger.warning(f"Failed to download image from {image_url}: {e}")

        return None

    def scrape_product_detail(self, detail_url: str) -> Optional[Dict]:
        """
        Stage 2 of scraping: visits the product page, parses metadata, and validates.
        """
        item_id = generate_item_id(detail_url)

        # Check if already scraped in checkpoint
        if self.checkpoint.is_item_scraped(item_id) and item_id in self.records_map:
            logger.info(f"⏭️ Skipping already scraped item ({item_id}) without network call.")
            return self.records_map[item_id]

        self._sleep_jitter()
        html = self.fetch_url(detail_url)
        if not html:
            logger.warning(f"Could not fetch product detail page: {detail_url}")
            return None

        record = parse_product_detail_page(html, detail_url)

        # Schema Validation
        is_valid, error_msg = validate_record(record)
        if not is_valid:
            logger.error(f"Record validation failed for {detail_url}: {error_msg}. Skipping item.")
            return None

        # Register in checkpoint
        self.checkpoint.register_item(record["item_id"])
        self.records_map[record["item_id"]] = record
        logger.info(
            f" [Item {len(self.records_map)}/{self.target_items}] "
            f"Extracted: '{record['full_title'][:35]}' | Price: £{record['price_gbp']:.2f} | Rating: {record['rating_stars']}★"
        )
        return record

    def run(self) -> List[Dict]:
        """
        Executes the main master-detail scraping loop with dynamic DOM pagination.
        Supports resume from checkpoint.
        """
        # Determine starting URL (resume from checkpoint if available)
        current_page_url = self.checkpoint.current_page_url or self.start_url
        pages_processed = len(self.checkpoint.completed_pages)

        logger.info("=" * 65)
        logger.info("🚀 STARTING E-COMMERCE INTELLIGENCE SCRAPER RUN")
        logger.info(f"Target Items : {self.target_items} unique records")
        logger.info(f"Max Pages    : {self.max_pages} consecutive catalog pages")
        logger.info(f"Initial URL  : {current_page_url}")
        logger.info(f"Resume State : {pages_processed} pages completed, {len(self.records_map)} items in memory")
        logger.info("=" * 65)

        try:
            while current_page_url and pages_processed < self.max_pages:
                # Check if we already hit target count
                if len(self.records_map) >= self.target_items:
                    logger.info(f"Reached target item count ({self.target_items}). Stopping pagination.")
                    break

                # If this page was already completed, we shouldn't re-crawl it
                if self.checkpoint.is_page_completed(current_page_url):
                    logger.info(f"Catalog page already marked completed in checkpoint: {current_page_url}")
                    # Fetch page only to get next page link dynamically
                    html = self.fetch_url(current_page_url)
                    if not html:
                        break
                    _, current_page_url = parse_catalog_page(html, current_page_url)
                    continue

                page_index = pages_processed + 1
                logger.info(f"\n📂 [CATALOG PAGE {page_index}/{self.max_pages}] Fetching: {current_page_url}")

                self._sleep_jitter()
                catalog_html = self.fetch_url(current_page_url)
                if not catalog_html:
                    logger.error(f"Failed to fetch catalog page: {current_page_url}. Aborting.")
                    break

                # Parse book links and dynamic NEXT link from DOM
                detail_urls, next_page_url = parse_catalog_page(catalog_html, current_page_url)
                logger.info(f"Found {len(detail_urls)} product pods on this catalog page.")
                if next_page_url:
                    logger.info(f"Dynamic 'next' link found: {next_page_url}")
                else:
                    logger.info("No further 'next' pagination link in DOM.")

                # Stage 2: Iterate through each product pod and scrape detail page
                for detail_url in detail_urls:
                    if len(self.records_map) >= self.target_items:
                        break
                    self.scrape_product_detail(detail_url)

                # Mark catalog page completed in checkpoint
                pages_processed += 1
                self.checkpoint.mark_page_completed(current_page_url, next_page_url or "")

                # Incremental disk save to prevent data loss
                save_records(list(self.records_map.values()))

                # Advance to next page via dynamic link
                current_page_url = next_page_url

        except KeyboardInterrupt:
            logger.warning("\n⚠️ Process interrupted by user (KeyboardInterrupt). Saving checkpoint...")
            self.checkpoint.save(current_page_url or "")
            save_records(list(self.records_map.values()))
            logger.info("Checkpoint and scraped records saved safely. You can resume anytime!")
            return list(self.records_map.values())

        # =====================================================================
        # Bonus Challenge: Top 10 highest-rated book cover image download
        # =====================================================================
        self._process_top_rated_images()

        # Final write to CSV and JSON
        all_records = list(self.records_map.values())
        save_records(all_records)
        logger.info(f" Scraping complete. Total unique records saved: {len(all_records)}")
        return all_records

    def _process_top_rated_images(self) -> None:
        """
        Identifies the top 10 highest-rated books, downloads their cover images,
        and links the local file paths into the records.
        """
        all_records = list(self.records_map.values())
        if not all_records:
            return

        logger.info("\n" + "=" * 65)
        logger.info(f"🎨 BONUS CHALLENGE: Downloading Top {TOP_RATED_DOWNLOAD_COUNT} Rated Book Covers")
        logger.info("=" * 65)

        # Sort by rating_stars descending, then price_gbp descending
        sorted_books = sorted(
            all_records,
            key=lambda x: (x.get("rating_stars", 0), x.get("price_gbp", 0.0)),
            reverse=True,
        )

        top_books = sorted_books[:TOP_RATED_DOWNLOAD_COUNT]
        for idx, book in enumerate(top_books, 1):
            image_url = book.get("cover_image_url")
            item_id = book.get("item_id")
            if image_url and item_id:
                local_path = self.download_image(image_url, item_id)
                if local_path:
                    # Update in records map
                    self.records_map[item_id]["local_image_path"] = local_path
                    logger.info(
                        f"   [{idx}/{TOP_RATED_DOWNLOAD_COUNT}] {book['full_title'][:30]} "
                        f"({book['rating_stars']}★) -> {local_path}"
                    )
