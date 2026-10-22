"""The MP3s live in the shared collection ``audio`` (kind ``audio.file``), one item per video.

    <root>/audio/by-app/youtube-to-mp3/yt-<video id>/<title>.mp3      the payload: one MP3, the primary
    <root>/audio/by-app/youtube-to-mp3/yt-<video id>/.item/...        manifest and thumbnail

Other apps (the Video Audio Mixer) read the collection and pick items by
their ref, ``audio:youtube-to-mp3/yt-<video id>``. Manifest ``meta``:
``duration`` (s, from the MP3), ``format`` ("mp3"), ``youtube_id``,
``channel``, ``channel_url``, ``license`` (YouTube's licence text, "" when
standard) and ``upload_date`` (YYYYMMDD).
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from reflex_ddns_auth.collections import Collection, Item
from reflex_ddns_auth.collections.refs import valid_item_id

COLLECTION = "audio"
KIND = "audio.file"
# Our owner name in the collection: the App Store subdomain. DDNS_APP_ID (set
# by the App Store) wins; a run on a laptop uses the same name, so its items
# are the same items.
APP_ID = "youtube-to-mp3"
FILENAME_MAX = 120


def audio() -> Collection:
    """The collection, resolved from the environment each time (cheap, no I/O)."""
    return Collection(COLLECTION, app_id=APP_ID)


def item_id(video_id: str) -> str:
    return f"yt-{video_id}"


def video_id_of(item: str) -> str:
    return item[3:] if item.startswith("yt-") else ""


def mp3_name(title: str) -> str:
    """A file name for the MP3: the title without path separators or control characters."""
    text = unicodedata.normalize("NFC", title or "")
    text = "".join(" " if unicodedata.category(c).startswith("C") else c for c in text)
    text = re.sub(r'[/\\:*?"<>|]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip().strip(".").strip()
    if text.startswith("-"):
        text = text.lstrip("-").strip()
    stem = text[: FILENAME_MAX - len(".mp3")].rstrip(" .")
    return f"{stem}.mp3" if stem else "audio.mp3"


def has(video_id: str) -> bool:
    try:
        return audio().has(item_id(video_id))
    except Exception:  # noqa: BLE001 - an unreadable tree means "not there"
        return False


def ref(video_id: str) -> str:
    return audio().ref(item_id(video_id))


def own_item(item: str) -> Item | None:
    """One of our own published items by its id, or ``None``."""
    if not valid_item_id(item):
        return None
    collection = audio()
    found = collection.get(collection.ref(item), remote=False)
    return found if found is not None and found.kind == KIND else None


def mp3_path(item: str) -> Path | None:
    found = own_item(item)
    path = found.primary if found is not None else None
    return path if path is not None and path.is_file() else None


def thumbnail_path(item: str) -> Path | None:
    found = own_item(item)
    return found.thumbnail if found is not None else None


def _clock(seconds: float) -> str:
    seconds = int(round(seconds or 0))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _size(n: int) -> str:
    return f"{n / 1_000_000:.1f} MB" if n >= 100_000 else f"{max(n, 0) / 1000:.0f} KB"


def rows() -> list[dict[str, Any]]:
    """Our items, newest first, as rows for the Library tab."""
    collection = audio()
    out = []
    for it in collection.local_items(KIND):
        if it.owner != collection.app_id:
            continue
        meta = it.meta
        duration = float(meta.get("duration") or 0.0)
        out.append(
            {
                "item": it.id,
                "ref": it.ref,
                "video_id": str(meta.get("youtube_id") or video_id_of(it.id)),
                "title": it.title,
                "channel": str(meta.get("channel") or ""),
                "license": str(meta.get("license") or ""),
                "duration": duration,
                "duration_text": _clock(duration),
                "size_text": _size(it.bytes),
                "created": it.created_at,
                "source": str(it.manifest.get("source") or ""),
            }
        )
    out.sort(key=lambda r: r["created"], reverse=True)
    return out


def remove(item: str) -> bool:
    """Delete one of our own items (other apps' items are never touched)."""
    if not valid_item_id(item) or own_item(item) is None:
        return False
    return audio().remove(item)
