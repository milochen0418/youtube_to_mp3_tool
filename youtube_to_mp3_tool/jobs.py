"""Conversions run in the backend, several at once, whoever started them.

A job downloads a video's audio (yt-dlp), converts it to MP3 (ffmpeg) and
publishes it as an item of the ``audio`` collection. At most
``YT2MP3_PARALLEL`` jobs (default 3) run at the same time; the others wait
in line. Jobs live in this process, shared by every open page: a page reads
``snapshot()`` and shows it, and stays out of the work itself.

    queued → fetching → downloading → converting → saving → done
                                                           ↘ failed | cancelled
"""

from __future__ import annotations

import logging
import os
import secrets
import shutil
import tempfile
import threading
import time
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable

from reflex_ddns_auth.collections import ItemExists, PublishError, QuotaExceeded

from youtube_to_mp3_tool import convert, library, youtube

log = logging.getLogger(__name__)

ACTIVE = ("queued", "fetching", "downloading", "converting", "saving")
FINISHED = ("done", "failed", "cancelled")
KEEP_FINISHED = 30

# Where each stage ends on the job's progress bar (percent).
_FETCHED, _DOWNLOADED, _CONVERTED = 3.0, 70.0, 97.0


def parallel_jobs() -> int:
    try:
        return max(1, min(8, int(os.environ.get("YT2MP3_PARALLEL", "3"))))
    except ValueError:
        return 3


def fetch_thumbnail(video_id: str) -> bytes | None:
    """The video's 320×180 JPEG from YouTube, or ``None``."""
    try:
        with urllib.request.urlopen(youtube.thumbnail_url(video_id), timeout=10) as resp:
            data = resp.read(512 * 1024 + 1)
    except OSError:
        return None
    return data if data.startswith(b"\xff\xd8\xff") and len(data) <= 512 * 1024 else None


@dataclass
class Job:
    id: str
    video_id: str
    title: str
    channel: str = ""
    duration: float = 0.0          # seconds, as the search showed it; the MP3's once done
    status: str = "queued"
    progress: float = 0.0          # 0..100
    detail: str = ""
    error: str = ""
    ref: str = ""
    created: float = field(default_factory=time.time)
    finished: float = 0.0
    cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    future: Future | None = field(default=None, repr=False)

    @property
    def active(self) -> bool:
        return self.status in ACTIVE

    def row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "video_id": self.video_id,
            "title": self.title,
            "channel": self.channel,
            "duration": self.duration,
            "status": self.status,
            "progress": round(self.progress, 1),
            "percent": f"{int(self.progress)}%",
            "detail": self.detail,
            "error": self.error,
            "ref": self.ref,
            "active": self.active,
            "finished": self.finished,
        }


def _mb(n: float) -> str:
    return f"{n / 1_000_000:.1f} MB"


class JobManager:
    """The conversions of this backend. Thread-safe; the work runs in a thread pool.

    ``download``, ``converter``, ``thumbnail`` and ``probe`` are the outside
    world (yt-dlp, ffmpeg, YouTube's thumbnails, ffprobe); tests replace them.
    """

    def __init__(
        self,
        workers: int | None = None,
        download: Callable[..., str] = youtube.download_audio,
        converter: Callable[..., None] = convert.to_mp3,
        thumbnail: Callable[[str], bytes | None] = fetch_thumbnail,
        probe: Callable[[str], float] = convert.duration_of,
        work_dir: str | None = None,
    ):
        self.workers = workers or parallel_jobs()
        self._pool = ThreadPoolExecutor(max_workers=self.workers, thread_name_prefix="yt2mp3")
        self._download = download
        self._convert = converter
        self._thumbnail = thumbnail
        self._probe = probe
        self._work_dir = work_dir or os.environ.get("YT2MP3_WORK_DIR") or None
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self.version = 0

    # -- what pages call ----------------------------------------------------

    def submit(self, video: dict[str, Any]) -> Job | None:
        """Queue a conversion of ``video`` ({"id", "title", "channel", "duration"}).

        Returns the job (the running one when this video is already being
        converted), or ``None`` when the MP3 is already in the library.
        """
        video_id = str(video.get("id") or "")
        if not video_id:
            return None
        with self._lock:
            for job in self._jobs.values():
                if job.video_id == video_id and job.active:
                    return job
        if library.has(video_id):
            return None
        job = Job(
            id=secrets.token_hex(4),
            video_id=video_id,
            title=str(video.get("title") or video_id),
            channel=str(video.get("channel") or ""),
            duration=float(video.get("duration") or 0.0),
            detail="Waiting for a free slot…",
        )
        with self._lock:
            self._jobs[job.id] = job
            self._trim()
            self.version += 1
        job.future = self._pool.submit(self._run, job)
        return job

    def cancel(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or not job.active:
                return
            job.cancel.set()
            if job.future is not None and job.future.cancel():
                # It never started.
                self._end(job, "cancelled", detail="Cancelled")
            else:
                job.detail = "Cancelling…"
                self.version += 1

    def retry(self, job_id: str) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.status not in ("failed", "cancelled"):
                return None
            job.status, job.progress, job.error, job.finished = "queued", 0.0, "", 0.0
            job.detail = "Waiting for a free slot…"
            job.cancel = threading.Event()
            job.created = time.time()
            self.version += 1
        job.future = self._pool.submit(self._run, job)
        return job

    def dismiss(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and not job.active:
                del self._jobs[job_id]
                self.version += 1

    def clear_finished(self) -> None:
        with self._lock:
            for job_id in [j.id for j in self._jobs.values() if not j.active]:
                del self._jobs[job_id]
            self.version += 1

    def snapshot(self) -> tuple[int, list[dict[str, Any]]]:
        """``(version, rows)``: running and waiting jobs first, then the finished ones, newest first."""
        with self._lock:
            jobs = list(self._jobs.values())
            version = self.version
        running = sorted((j for j in jobs if j.active), key=lambda j: j.created)
        finished = sorted((j for j in jobs if not j.active), key=lambda j: j.finished, reverse=True)
        return version, [j.row() for j in running + finished]

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for j in self._jobs.values() if j.active)

    def wait(self, timeout: float = 30.0) -> bool:
        """Until no job is running or waiting (tests)."""
        end = time.time() + timeout
        while time.time() < end:
            if self.active_count() == 0:
                return True
            time.sleep(0.02)
        return False

    # -- the work -------------------------------------------------------------

    def _trim(self) -> None:
        finished = sorted((j for j in self._jobs.values() if not j.active), key=lambda j: j.finished)
        for job in finished[: max(0, len(finished) - KEEP_FINISHED)]:
            del self._jobs[job.id]

    def _set(self, job: Job, **fields: Any) -> None:
        with self._lock:
            changed = any(getattr(job, k) != v for k, v in fields.items())
            if not changed:
                return
            for key, value in fields.items():
                setattr(job, key, value)
            self.version += 1

    def _end(self, job: Job, status: str, **fields: Any) -> None:
        """Finish ``job``; the caller holds the lock."""
        job.status = status
        job.finished = time.time()
        for key, value in fields.items():
            setattr(job, key, value)
        self.version += 1

    def _finish(self, job: Job, status: str, **fields: Any) -> None:
        with self._lock:
            self._end(job, status, **fields)
        log.info("Job %s (%s) %s %s", job.id, job.video_id, status, job.error or job.detail)

    def _run(self, job: Job) -> None:
        if job.cancel.is_set():
            self._finish(job, "cancelled", detail="Cancelled")
            return
        log.info("Job %s (%s) starts: %s", job.id, job.video_id, job.title)
        work = tempfile.mkdtemp(prefix="yt2mp3-", dir=self._work_dir)
        try:
            self._convert_one(job, work)
        except youtube.Cancelled:
            self._finish(job, "cancelled", detail="Cancelled")
        except QuotaExceeded as e:
            self._finish(job, "failed", error=f"No room left in the audio collection: {e}", detail="")
        except PublishError as e:
            self._finish(job, "failed", error=f"Could not save the MP3: {e}", detail="")
        except BaseException as e:  # noqa: BLE001 - every failure ends the job visibly
            if job.cancel.is_set():
                self._finish(job, "cancelled", detail="Cancelled")
            else:
                log.warning("Job %s (%s) failed", job.id, job.video_id, exc_info=True)
                self._finish(job, "failed", error=youtube.error_message(e), detail="")
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _convert_one(self, job: Job, work: str) -> None:
        collection = library.audio()
        item_id = library.item_id(job.video_id)
        self._set(job, status="fetching", progress=1.0, detail="Reading the video's details…")
        if collection.has(item_id):
            self._finish(job, "done", progress=100.0, ref=collection.ref(item_id), detail="Already in the library")
            return

        info: dict[str, Any] = {}
        last = [0.0]

        def on_details(details: dict[str, Any]) -> None:
            info.update(details)
            self._set(
                job,
                title=str(details.get("title") or job.title),
                channel=str(details.get("channel") or details.get("uploader") or job.channel),
                duration=float(details.get("duration") or job.duration or 0.0),
                status="downloading",
                progress=_FETCHED,
                detail="Starting the download…",
            )

        def on_download(done: float, total: float, speed: float) -> None:
            now = time.time()
            if now - last[0] < 0.25 and done < total:
                return
            last[0] = now
            share = done / total if total > 0 else 0.0
            detail = f"{_mb(done)} of {_mb(total)}" if total > 0 else _mb(done)
            if speed > 0:
                detail += f" · {speed / 1_000_000:.1f} MB/s"
            self._set(job, progress=_FETCHED + share * (_DOWNLOADED - _FETCHED), detail=detail)

        source = self._download(job.video_id, work, on_details, on_download, job.cancel.is_set)
        self._set(job, status="converting", progress=_DOWNLOADED, detail="Converting to MP3…")

        name = library.mp3_name(job.title)
        meta = {
            "duration": float(job.duration or 0.0),
            "format": "mp3",
            "youtube_id": job.video_id,
            "channel": job.channel,
            "channel_url": str(info.get("channel_url") or info.get("uploader_url") or ""),
            "license": str(info.get("license") or ""),
            "upload_date": str(info.get("upload_date") or ""),
        }
        tags = {"title": job.title, "artist": job.channel, "comment": youtube.watch_url(job.video_id)}

        def on_convert(fraction: float) -> None:
            self._set(
                job,
                progress=_DOWNLOADED + fraction * (_CONVERTED - _DOWNLOADED),
                detail=f"Converting to MP3… {int(fraction * 100)}%",
            )

        try:
            publish = collection.publish(
                item_id, kind=library.KIND, title=job.title, source=youtube.watch_url(job.video_id),
                primary=name, meta=meta,
            )
            with publish as item:
                try:
                    part = item.file(name + ".part")
                    self._convert(source, str(part), job.duration, tags, on_convert, job.cancel.is_set)
                    os.replace(part, item.file(name))
                    self._set(job, status="saving", progress=_CONVERTED, detail="Saving to the library…")
                    picture = self._thumbnail(job.video_id)
                    if picture:
                        try:
                            item.set_thumbnail(picture)
                        except PublishError:
                            pass
                    seconds = self._probe(str(item.file(name)))
                    if seconds > 0:
                        item.meta["duration"] = round(seconds, 3)
                    if job.cancel.is_set():
                        raise youtube.Cancelled()
                except BaseException:
                    item.discard()
                    raise
        except ItemExists:
            pass  # someone else published the same video meanwhile: it is there
        seconds = self._duration_of(collection, item_id) or float(meta["duration"])
        self._finish(
            job, "done", progress=100.0, ref=collection.ref(item_id), duration=seconds,
            detail=name,
        )

    @staticmethod
    def _duration_of(collection, item_id: str) -> float:
        item = collection.get(collection.ref(item_id), remote=False)
        return float((item.meta.get("duration") if item else 0) or 0.0)


_manager: JobManager | None = None
_manager_lock = threading.Lock()


def manager() -> JobManager:
    """The backend's job manager (created on first use)."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = JobManager()
            try:
                library.audio().gc_tmp()
            except Exception:  # noqa: BLE001 - housekeeping only
                pass
        return _manager
