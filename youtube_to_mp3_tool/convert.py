"""MP3 conversion with ffmpeg, reporting progress, and reading a file's duration with ffprobe."""

from __future__ import annotations

import json
import subprocess
import threading
from typing import Callable

from youtube_to_mp3_tool.youtube import Cancelled


def duration_of(path: str) -> float:
    """Seconds of audio in ``path`` (0.0 when ffprobe cannot tell)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return float(json.loads(out.stdout or "{}").get("format", {}).get("duration") or 0.0)
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0.0


def to_mp3(
    source: str,
    target: str,
    duration: float,
    tags: dict[str, str],
    on_progress: Callable[[float], None],
    cancelled: Callable[[], bool],
) -> None:
    """Convert ``source`` into the MP3 file ``target`` (VBR ~190 kb/s, ID3v2.3 tags).

    ``target`` may have any extension (e.g. ``.mp3.part``): the format is given
    explicitly. ``on_progress(fraction)`` follows ffmpeg's ``-progress`` output.
    """
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-i", source, "-vn", "-map_metadata", "-1"]
    cmd += ["-c:a", "libmp3lame", "-q:a", "2", "-id3v2_version", "3"]
    for key, value in tags.items():
        if value:
            cmd += ["-metadata", f"{key}={value}"]
    cmd += ["-progress", "pipe:1", "-nostats", "-f", "mp3", target]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace")
    errors: list[str] = []
    # Drain stderr on the side so a chatty ffmpeg never blocks on a full pipe.
    drain = threading.Thread(target=lambda: errors.extend(proc.stderr.readlines()), daemon=True)
    drain.start()
    try:
        for line in proc.stdout:
            if cancelled():
                proc.kill()
                raise Cancelled()
            key, _, value = line.strip().partition("=")
            if key in ("out_time_us", "out_time_ms") and duration > 0:
                try:
                    on_progress(min(1.0, max(0.0, int(value) / 1_000_000 / duration)))
                except ValueError:
                    pass
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        drain.join(timeout=5)
    if cancelled():
        raise Cancelled()
    if proc.returncode != 0:
        tail = next((e.strip() for e in reversed(errors) if e.strip()), "")
        raise RuntimeError(f"ffmpeg could not convert the audio ({tail[:160] or proc.returncode})")
    on_progress(1.0)
