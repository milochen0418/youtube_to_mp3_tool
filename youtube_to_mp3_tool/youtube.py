"""YouTube through yt-dlp: search like youtube.com, read a video's details, download its audio.

Everything here blocks; callers run it in a thread.

Search uses YouTube's own results page with its ``sp`` filter parameter, a
base64 protobuf: field 1 = sort order, field 2 = the filters (1 upload date,
2 type, 3 duration, 6 Creative Commons). Checked against live results on
2026-10-22: duration, Creative Commons, upload date and "most viewed" filter
as on youtube.com; sorting by upload date no longer changes YouTube's order,
so "newest" is offered as an upload-date filter instead.
"""

from __future__ import annotations

import base64
import re
from typing import Any, Callable
from urllib.parse import parse_qs, urlencode, urlparse

import yt_dlp

PAGE_SIZE = 20

SORTS = {"relevance": 0, "views": 3}
DURATIONS = {"any": 0, "short": 1, "medium": 3, "long": 2}  # < 4 min, 4-20 min, > 20 min
UPLOADED = {"any": 0, "week": 3, "month": 4, "year": 5}

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YOUTUBE_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")


class Cancelled(Exception):
    """Raised from the download hook when the job was cancelled."""


class _QuietLogger:
    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        pass


def base_options() -> dict[str, Any]:
    """yt-dlp options shared by every call.

    yt-dlp's own player clients give the audio-only streams (Opus ~140 kb/s);
    the tv/android/ios clients the old version forced only offer a 360p
    video's sound. YouTube's JavaScript challenge needs a runtime: deno, node
    (22+) or bun, whichever is installed (the App Store image has node 22 and bun).
    """
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _QuietLogger(),
        "noplaylist": True,
        "no_color": True,
        "geo_bypass": True,
        "http_headers": {"User-Agent": _USER_AGENT},
        "js_runtimes": {"deno": {}, "node": {}, "bun": {}},
        "extractor_retries": 3,
        "fragment_retries": 3,
        "retries": 5,
        "retry_sleep_functions": {"http": lambda n: 0.5 * n},
    }


# -- search ------------------------------------------------------------------


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def search_params(sort: str = "relevance", duration: str = "any", uploaded: str = "any", cc_only: bool = False) -> str:
    """YouTube's ``sp`` value for these filters (always videos only)."""
    filters = b""
    if UPLOADED.get(uploaded, 0):
        filters += b"\x08" + _varint(UPLOADED[uploaded])
    filters += b"\x10\x01"
    if DURATIONS.get(duration, 0):
        filters += b"\x18" + _varint(DURATIONS[duration])
    if cc_only:
        filters += b"\x30\x01"
    message = b""
    if SORTS.get(sort, 0):
        message += b"\x08" + _varint(SORTS[sort])
    message += b"\x12" + _varint(len(filters)) + filters
    return base64.b64encode(message).decode("ascii")


def search_url(query: str, **filters: Any) -> str:
    return "https://www.youtube.com/results?" + urlencode({"search_query": query, "sp": search_params(**filters)})


def youtube_link(text: str) -> tuple[str, str] | None:
    """``("video", id)`` or ``("playlist", url)`` when ``text`` is a YouTube link, else ``None``."""
    text = (text or "").strip()
    if not re.match(r"^(https?://)?([\w-]+\.)*(youtube\.com|youtu\.be|youtube-nocookie\.com)/", text, re.I):
        return None
    url = urlparse(text if "://" in text else "https://" + text)
    host = (url.hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in _YOUTUBE_HOSTS):
        return None
    query = parse_qs(url.query)
    path = url.path.rstrip("/")
    if host.endswith("youtu.be"):
        vid = path.lstrip("/").split("/")[0]
        return ("video", vid) if _VIDEO_ID.match(vid) else None
    if query.get("v") and _VIDEO_ID.match(query["v"][0]):
        return ("video", query["v"][0])
    match = re.match(r"^/(shorts|embed|live|v)/([A-Za-z0-9_-]{11})$", path)
    if match:
        return ("video", match.group(2))
    if query.get("list"):
        return ("playlist", f"https://www.youtube.com/playlist?list={query['list'][0]}")
    return None


def watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def thumbnail_url(video_id: str) -> str:
    return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"


def _entry(e: dict[str, Any]) -> dict[str, Any] | None:
    """A search or playlist entry as a result row; ``None`` for channels, playlists and the like."""
    vid = str(e.get("id") or "")
    if not _VIDEO_ID.match(vid):
        return None
    if e.get("ie_key") not in (None, "Youtube") or e.get("_type") not in (None, "url", "video"):
        return None
    duration = e.get("duration")
    live = e.get("live_status") in ("is_live", "is_upcoming") or (duration is None and e.get("_type") == "url")
    return {
        "id": vid,
        "title": str(e.get("title") or vid),
        "channel": str(e.get("channel") or e.get("uploader") or ""),
        "duration": float(duration) if duration else 0.0,
        "views": int(e.get("view_count") or 0),
        "live": bool(live),
    }


def _flat(url: str, limit: int) -> list[dict[str, Any]]:
    opts = {**base_options(), "extract_flat": "in_playlist", "skip_download": True, "playlistend": limit}
    opts["noplaylist"] = False
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") if info else None
    if entries is None:  # a single video
        entries = [info] if info else []
    return list(entries)


def search(
    query: str,
    limit: int = PAGE_SIZE,
    sort: str = "relevance",
    duration: str = "any",
    uploaded: str = "any",
    cc_only: bool = False,
) -> tuple[list[dict[str, Any]], bool]:
    """``(rows, more)``: up to ``limit`` videos for ``query``, and whether YouTube has more.

    A YouTube link instead of words shows that video, or the videos of a playlist.
    """
    link = youtube_link(query)
    if link and link[0] == "video":
        return [video(link[1])], False
    if link:
        entries = _flat(link[1], limit)
    else:
        entries = _flat(search_url(query, sort=sort, duration=duration, uploaded=uploaded, cc_only=cc_only), limit)
    rows, seen = [], set()
    for e in entries:
        row = _entry(e)
        if row is not None and row["id"] not in seen:
            seen.add(row["id"])
            rows.append(row)
    return rows[:limit], len(entries) >= limit


def video(video_id: str) -> dict[str, Any]:
    """One video as a result row (for a pasted link)."""
    row = _entry({"_type": "video", **details(video_id)})
    if row is None:
        raise ValueError(f"not a YouTube video: {video_id}")
    return row


# -- one video -----------------------------------------------------------------


def details(video_id: str) -> dict[str, Any]:
    """The full details of a video, without downloading it."""
    with yt_dlp.YoutubeDL(base_options()) as ydl:
        info = ydl.extract_info(watch_url(video_id), download=False, process=False)
    return dict(info or {})


class NotConvertible(Exception):
    """The video cannot become an MP3 (yet): a live stream or a premiere."""


def download_audio(
    video_id: str,
    folder: str,
    on_details: Callable[[dict[str, Any]], None],
    on_progress: Callable[[float, float, float], None],
    cancelled: Callable[[], bool],
) -> str:
    """Download the best audio-only stream of a video into ``folder``; returns its path.

    ``on_details(info)`` gets the video's details before the download starts
    (title, channel, licence...); ``on_progress(done_bytes, total_bytes, speed)``
    follows the download. When ``cancelled()`` turns true it stops with ``Cancelled``.
    """

    def hook(d: dict[str, Any]) -> None:
        if cancelled():
            raise Cancelled()
        if d.get("status") == "downloading":
            total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
            on_progress(float(d.get("downloaded_bytes") or 0), total, float(d.get("speed") or 0))

    opts = {
        **base_options(),
        "format": "bestaudio/best",
        "outtmpl": {"default": f"{folder}/source.%(ext)s"},
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(watch_url(video_id), download=False)
        if (info or {}).get("live_status") in ("is_live", "is_upcoming", "post_live"):
            raise NotConvertible("Live streams and premieres can't be converted until they are over.")
        on_details(dict(info or {}))
        if cancelled():
            raise Cancelled()
        info = ydl.process_ie_result(info, download=True)
    if cancelled():
        raise Cancelled()
    downloads = (info or {}).get("requested_downloads") or []
    path = downloads[0].get("filepath") if downloads else None
    if not path:
        raise FileNotFoundError("yt-dlp finished without a file")
    return str(path)


def error_message(error: BaseException) -> str:
    """A short sentence for what went wrong with YouTube."""
    text = str(error).lower()
    if "sign in to confirm" in text or "confirm your age" in text or "authentication" in text:
        return "YouTube wants a signed-in user for this video (age limit or bot check). Try another one."
    if "http error 403" in text or "unable to download video data" in text:
        return "YouTube refused the download. Try again later, or another video."
    if "private" in text:
        return "This video is private."
    if "unavailable" in text or "removed" in text or "does not exist" in text:
        return "This video is unavailable or was removed."
    if "copyright" in text:
        return "This video is blocked for copyright reasons."
    if "live event" in text or "is live" in text or "premiere" in text:
        return "Live streams and premieres can't be converted until they are over."
    if "timed out" in text or "network" in text or "connection" in text or "resolve" in text:
        return "Could not reach YouTube. Check the network and try again."
    first = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
    first = re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*)?([\w-]{11}:\s*)?", "", first)
    return first[:160]
