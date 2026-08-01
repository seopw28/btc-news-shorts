"""
YouTube API quota manager — prevents quota exceeded errors.

YouTube Data API v3 daily quota: 50,000 units (resets at midnight Pacific Time).
Cost per operation:
  - videos.insert (upload):   1600 units
  - captions.insert:           400 units
  - videos.list:                 1 unit

Per-language upload = 1600 + 400 = 2000 units
Full 3-lang run = 6000 units (+ minor reads)

Usage:
    from src.quota_manager import QuotaManager
    qm = QuotaManager()
    if qm.can_upload(lang="en"):
        upload_video(...)
        qm.record_upload(lang="en")
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config.settings import BASE_DIR

QUOTA_FILE = BASE_DIR / "_internal" / "data" / "youtube_quota.json"
DAILY_LIMIT = 50_000

# YouTube quota costs
COSTS = {
    "video_upload": 1600,
    "caption_insert": 400,
    "video_list": 1,
}

# Quota resets at midnight Pacific Time (UTC-7 or UTC-8 depending on DST)
PT_OFFSET = timedelta(hours=-7)  # PDT (March-November)


def _today_pt() -> str:
    """Get today's date in Pacific Time as YYYY-MM-DD."""
    now_utc = datetime.now(timezone.utc)
    now_pt = now_utc + PT_OFFSET
    return now_pt.strftime("%Y-%m-%d")


class QuotaManager:
    def __init__(self):
        self.data = self._load()

    def _load(self) -> dict:
        if QUOTA_FILE.exists():
            try:
                with open(QUOTA_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save(self):
        QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(QUOTA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _today_entry(self) -> dict:
        today = _today_pt()
        if self.data.get("date") != today:
            # New day — reset
            self.data = {"date": today, "used": 0, "uploads": [], "errors": []}
            self._save()
        return self.data

    def used_today(self) -> int:
        return self._today_entry().get("used", 0)

    def remaining_today(self) -> int:
        return DAILY_LIMIT - self.used_today()

    def can_upload(self, include_caption: bool = True) -> bool:
        """Check if there's enough quota for one video upload (+caption)."""
        cost = COSTS["video_upload"]
        if include_caption:
            cost += COSTS["caption_insert"]
        return self.remaining_today() >= cost

    def can_upload_all(self, lang_count: int = 3) -> tuple[bool, int]:
        """Check if there's enough quota for a full multi-lang run.
        Returns (can_proceed, max_uploadable_count).
        """
        cost_per_lang = COSTS["video_upload"] + COSTS["caption_insert"]
        remaining = self.remaining_today()
        max_count = remaining // cost_per_lang
        return max_count >= lang_count, min(max_count, lang_count)

    def record_usage(self, operation: str, lang: str = "", cost: int = None):
        """Record a quota-consuming operation."""
        entry = self._today_entry()
        if cost is None:
            cost = COSTS.get(operation, 0)
        entry["used"] = entry.get("used", 0) + cost
        entry["uploads"].append({
            "operation": operation,
            "lang": lang,
            "cost": cost,
            "time": datetime.now().isoformat(),
        })
        self._save()

    def record_upload(self, lang: str):
        """Shortcut: record a video upload."""
        self.record_usage("video_upload", lang=lang)

    def record_caption(self, lang: str):
        """Shortcut: record a caption upload."""
        self.record_usage("caption_insert", lang=lang)

    def record_error(self, lang: str, error: str):
        """Record a quota error for diagnostics."""
        entry = self._today_entry()
        entry["errors"].append({
            "lang": lang,
            "error": error[:200],
            "time": datetime.now().isoformat(),
        })
        self._save()

    def summary(self) -> str:
        """Human-readable quota summary."""
        entry = self._today_entry()
        used = entry.get("used", 0)
        uploads = [u for u in entry.get("uploads", []) if u["operation"] == "video_upload"]
        return (
            f"[Quota] {used:,}/{DAILY_LIMIT:,} used today ({_today_pt()} PT)\n"
            f"  Remaining: {DAILY_LIMIT - used:,} units\n"
            f"  Uploads today: {len(uploads)} videos\n"
            f"  Can upload: {self.remaining_today() // (COSTS['video_upload'] + COSTS['caption_insert'])} more videos"
        )


# Convenience functions for use in pipeline
def check_quota(lang_count: int = 3) -> tuple[bool, int, str]:
    """Pre-flight quota check. Returns (ok, max_uploadable, summary_message)."""
    qm = QuotaManager()
    ok, max_count = qm.can_upload_all(lang_count)
    summary = qm.summary()
    return ok, max_count, summary
