"""
Checkpoint and state persistence module.
Manages scraper_state.json to ensure interrupted runs resume automatically
without duplicating records.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

from .config import CHECKPOINT_FILE_PATH

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Tracks completed catalog page URLs and individual item IDs.
    Persists progress to disk after each catalog page or batch.
    """

    def __init__(self, checkpoint_path: Path = CHECKPOINT_FILE_PATH):
        self.checkpoint_path = checkpoint_path
        self.completed_pages: Set[str] = set()
        self.current_page_url: str = ""
        self.scraped_item_ids: Set[str] = set()
        self.pages_processed_count: int = 0
        self.load()

    def load(self) -> None:
        """Loads state from checkpoint file if present."""
        if not self.checkpoint_path.exists():
            logger.info("No existing checkpoint found. Starting a fresh run.")
            return

        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.completed_pages = set(data.get("completed_pages", []))
            self.current_page_url = data.get("current_page_url", "")
            self.scraped_item_ids = set(data.get("scraped_item_ids", []))
            self.pages_processed_count = data.get("pages_processed_count", len(self.completed_pages))

            logger.info(
                f"Checkpoint resumed: {len(self.completed_pages)} pages completed, "
                f"{len(self.scraped_item_ids)} items previously scraped."
            )
        except Exception as e:
            logger.warning(f"Failed to read checkpoint file ({e}). Starting fresh.")

    def save(self, next_page_url: str = "") -> None:
        """Atomically saves the current progress to disk."""
        data = {
            "completed_pages": list(self.completed_pages),
            "current_page_url": next_page_url or self.current_page_url,
            "scraped_item_ids": list(self.scraped_item_ids),
            "pages_processed_count": len(self.completed_pages),
            "last_updated": datetime.now().isoformat(),
        }

        # Save to temp file and rename for atomic write safety
        temp_path = self.checkpoint_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self.checkpoint_path)
            logger.debug(f"Checkpoint saved: {len(self.completed_pages)} pages, {len(self.scraped_item_ids)} items.")
        except Exception as e:
            logger.error(f"Error saving checkpoint: {e}")

    def is_item_scraped(self, item_id: str) -> bool:
        """Returns True if the item has already been successfully scraped."""
        return item_id in self.scraped_item_ids

    def register_item(self, item_id: str) -> None:
        """Registers a newly scraped item ID."""
        self.scraped_item_ids.add(item_id)

    def mark_page_completed(self, page_url: str, next_page_url: str) -> None:
        """Marks a catalog page as fully scraped and updates next page pointer."""
        self.completed_pages.add(page_url)
        self.current_page_url = next_page_url
        self.save(next_page_url=next_page_url)

    def is_page_completed(self, page_url: str) -> bool:
        """Checks if a catalog page was already completed in a previous run."""
        return page_url in self.completed_pages

    def reset(self) -> None:
        """Clears the checkpoint file for a fresh start."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
        self.completed_pages.clear()
        self.current_page_url = ""
        self.scraped_item_ids.clear()
        self.pages_processed_count = 0
        logger.info("Checkpoint state reset.")
