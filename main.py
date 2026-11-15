"""
Main entry point for the Fault-Tolerant E-Commerce Scraper.
Runs the master-detail scraping pipeline, checkpoint manager, and displays analytics summary.
"""
import argparse
import logging
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.checkpoint import CheckpointManager
from core.config import CSV_FILE_PATH, JSON_FILE_PATH, MAX_PAGES, TARGET_ITEMS
from core.scraper import EcommerceScraper
from core.storage import compute_analytics_summary, print_console_summary


def setup_logging(verbose: bool = False) -> None:
    """Configures structured, informative logging."""
    log_level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = [handler]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="E-Commerce Intelligence Fault-Tolerant Web Scraper (Books to Scrape)"
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset existing checkpoint state and start a fresh scrape from page 1.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=MAX_PAGES,
        help=f"Number of consecutive catalog pages to scrape (default: {MAX_PAGES}).",
    )
    parser.add_argument(
        "--items",
        type=int,
        default=TARGET_ITEMS,
        help=f"Target number of unique items to scrape (default: {TARGET_ITEMS}).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed debug logs.",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.reset:
        logging.info("🧹 Resetting existing checkpoint and state files...")
        cp = CheckpointManager()
        cp.reset()
        if CSV_FILE_PATH.exists():
            CSV_FILE_PATH.unlink()
        if JSON_FILE_PATH.exists():
            JSON_FILE_PATH.unlink()
        logging.info("Clean state ready.")

    scraper = EcommerceScraper(max_pages=args.pages, target_items=args.items)
    records = scraper.run()

    # Generate and display analytical summary
    if records:
        summary = compute_analytics_summary(records)
        print_console_summary(summary)
        print("📁 Output Artifacts:")
        print(f"   • CSV Dataset  : {CSV_FILE_PATH.resolve()}")
        print(f"   • JSON Dataset : {JSON_FILE_PATH.resolve()}")
        print(f"   • Checkpoint   : {CSV_FILE_PATH.parent / 'scraper_state.json'}")
        print(f"   • Media Folder : {CSV_FILE_PATH.parent.parent / 'media'}\n")
    else:
        logging.warning("No records were collected.")


if __name__ == "__main__":
    main()
