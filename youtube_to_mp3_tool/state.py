"""The finder page: search, preview, the conversions (shared by every page) and the library.

The same page runs on its own (``/``) and inside another app's dialog
(``/intent/audio-find``, DDNS Intent action ``audio.find``). In a dialog it
tells the caller what happens, without closing (``intent_update``):

    {"event": "started", "id": <video id>, "title": ...}            a conversion was queued here
    {"event": "ready", "ref": "audio:youtube-to-mp3/yt-<id>", "id", "title", "duration"}
                                                                     an MP3 was saved (any conversion
                                                                     finishing while the page is open)
    {"event": "failed", "id", "title", "error"}                      a conversion failed
    {"event": "pick", "ref", "title", "duration"}                   the user pressed "Use"

and "Done" answers the dialog with ``{"refs": [<refs saved while it was open>]}``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import reflex as rx
from reflex_ddns_auth.intent import IntentPage, intent_update

from youtube_to_mp3_tool import jobs, library, youtube

POLL_SECONDS = 0.5
# A page's loop beats every POLL_SECONDS; one silent for longer died (e.g. the backend restarted).
BEAT_SECONDS = 3.0
ACTIVE = jobs.ACTIVE


def _clock(seconds: float) -> str:
    seconds = int(round(seconds or 0))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _views(n: int) -> str:
    if n <= 0:
        return ""
    for size, unit in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if n >= size:
            value = n / size
            text = f"{value:.1f}".rstrip("0").rstrip(".") if value < 10 else f"{value:.0f}"
            return f"{text}{unit} views"
    return f"{n} views"


def _result_row(r: dict[str, Any]) -> dict[str, str]:
    return {
        "id": r["id"],
        "title": r["title"],
        "channel": r["channel"],
        "duration": str(r["duration"]),
        "duration_text": "LIVE" if r["live"] else (_clock(r["duration"]) if r["duration"] else ""),
        "views_text": _views(r["views"]),
        "live": "1" if r["live"] else "",
        "thumb": youtube.thumbnail_url(r["id"]),
        "watch": youtube.watch_url(r["id"]),
    }


def _job_row(j: dict[str, Any]) -> dict[str, str]:
    return {
        "id": j["id"],
        "video_id": j["video_id"],
        "title": j["title"],
        "channel": j["channel"],
        "duration": str(j["duration"]),
        "status": j["status"],
        "progress": f"{j['progress']:.1f}",
        "percent": j["percent"],
        "detail": j["detail"],
        "error": j["error"],
        "ref": j["ref"],
        "active": "1" if j["active"] else "",
        "finished": str(j["finished"]),
    }


def _library_row(r: dict[str, Any]) -> dict[str, str]:
    return {
        **{k: str(v) for k, v in r.items()},
        "cc": "1" if "creative commons" in r["license"].lower() else "",
    }


def ready_update(job: dict[str, str]) -> dict[str, Any]:
    return {
        "event": "ready",
        "ref": job["ref"],
        "id": job["video_id"],
        "title": job["title"],
        "duration": float(job["duration"] or 0),
    }


def failed_update(job: dict[str, str]) -> dict[str, Any]:
    return {"event": "failed", "id": job["video_id"], "title": job["title"], "error": job["error"]}


def pick_update(ref: str, title: str, duration: str) -> dict[str, Any]:
    try:
        seconds = float(duration or 0)
    except ValueError:
        seconds = 0.0
    return {"event": "pick", "ref": ref, "title": title, "duration": seconds}


class FinderState(rx.State):
    # -- search
    query: str = ""
    searched: str = ""
    searching: bool = False
    search_error: str = ""
    results: list[dict[str, str]] = []
    more: bool = False
    limit: int = youtube.PAGE_SIZE
    sort: str = "relevance"
    duration: str = "any"
    uploaded: str = "any"
    cc_only: bool = False
    preview_id: str = ""
    tab: str = "search"
    # -- conversions (a copy of the backend's job list) and the library
    jobs: list[dict[str, str]] = []
    library: list[dict[str, str]] = []
    playing: str = ""
    confirm_delete: str = ""
    # -- in a caller's dialog: the refs saved while it was open (for "Done")
    dialog_refs: list[str] = []

    _version: int = -1
    _watch_beat: float = 0.0
    _opened_at: float = 0.0
    _told: list[str] = []
    _search_seq: int = 0

    # -- what the page shows -------------------------------------------------

    @rx.var
    def result_rows(self) -> list[dict[str, str]]:
        """The results, each with what this app knows about it: in the library, converting..."""
        saved = {r["video_id"]: r for r in self.library}
        latest: dict[str, dict[str, str]] = {}
        for job in self.jobs:  # running first, then the newest finished
            latest.setdefault(job["video_id"], job)
        rows = []
        for r in self.results:
            job = latest.get(r["id"])
            item = saved.get(r["id"])
            if item is not None:
                state, ref, seconds = "library", item["ref"], item["duration"]
            elif job is not None and job["status"] != "done":
                state, ref, seconds = job["status"], job["ref"], job["duration"]
            else:
                # Never converted, or converted and deleted from the library since.
                state, ref, seconds = "", "", r["duration"]
            rows.append(
                {
                    **r,
                    "state": state,
                    "job": job["id"] if job else "",
                    "percent": job["percent"] if job else "",
                    "ref": ref,
                    "seconds": seconds,
                    "busy": "1" if state in ACTIVE else "",
                }
            )
        return rows

    @rx.var
    def active_count(self) -> int:
        return sum(1 for j in self.jobs if j["active"])

    @rx.var
    def done_count(self) -> int:
        return sum(1 for j in self.jobs if j["status"] == "done")

    @rx.var
    def finished_count(self) -> int:
        return sum(1 for j in self.jobs if not j["active"])

    @rx.var
    def pip_title(self) -> str:
        active, done = self.active_count, self.done_count
        if not active and not done:
            return "No conversions yet"
        parts = [f"Converting {active}"] if active else []
        if done:
            parts.append(f"{done} done")
        return " · ".join(parts)

    @rx.var
    def pip_jobs(self) -> list[dict[str, str]]:
        """What the picture-in-picture window shows: running jobs, then the latest finished ones."""
        running = [j for j in self.jobs if j["active"]]
        finished = [j for j in self.jobs if not j["active"]][: max(0, 4 - len(running))]
        return (running + finished)[:6]

    # -- opening ---------------------------------------------------------------

    def _refresh_library(self) -> None:
        try:
            self.library = [_library_row(r) for r in library.rows()]
        except Exception:  # noqa: BLE001 - an unreadable tree shows as empty
            logging.exception("Reading the audio collection failed")
            self.library = []

    def _apply(self, version: int, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Show the backend's jobs; returns the news a caller's dialog has not heard yet."""
        before = {j["id"]: j["status"] for j in self.jobs}
        self._version = version
        self.jobs = [_job_row(j) for j in rows]
        if any(j["status"] == "done" and before.get(j["id"]) != "done" for j in self.jobs):
            self._refresh_library()
        news = []
        for job in self.jobs:
            if job["active"] or job["id"] in self._told or float(job["finished"] or 0) < self._opened_at:
                continue
            if job["status"] == "done" and job["ref"]:
                news.append(ready_update(job))
                if job["ref"] not in self.dialog_refs:
                    self.dialog_refs = [*self.dialog_refs, job["ref"]]
            elif job["status"] == "failed":
                news.append(failed_update(job))
            self._told = [*self._told, job["id"]]
        return news

    def _start(self) -> list:
        self._opened_at = time.time()
        self._told = []
        self.dialog_refs = []
        self.preview_id = ""
        self.confirm_delete = ""
        self._refresh_library()
        version, rows = jobs.manager().snapshot()
        self._apply(version, rows)
        return [FinderState.watch] if any(r["active"] for r in rows) else []

    @rx.event
    def load(self):
        """The page on its own (``/``)."""
        return self._start()

    @rx.event
    def open_intent(self, params: dict):
        """The page in a caller's dialog: ``q`` searches right away."""
        events = self._start()
        q = str(params.get("q") or "").strip()
        if q:
            self.query = q
            events.append(FinderState.search)
        return events

    # -- search ------------------------------------------------------------------

    @rx.event
    def set_query(self, value: str):
        self.query = value

    @rx.event
    def submit_search(self, form: dict):
        self.query = str(form.get("q") or "").strip()
        return FinderState.search

    @rx.event
    def search(self):
        if not self.query.strip():
            return
        self.limit = youtube.PAGE_SIZE
        self.tab = "search"
        return FinderState.run_search

    @rx.event
    def more_results(self):
        self.limit += youtube.PAGE_SIZE
        return FinderState.run_search

    def _refilter(self):
        if self.searched:
            self.limit = youtube.PAGE_SIZE
            return FinderState.run_search

    @rx.event
    def set_sort(self, value: str):
        self.sort = value if value in youtube.SORTS else "relevance"
        return self._refilter()

    @rx.event
    def set_duration(self, value: str):
        self.duration = value if value in youtube.DURATIONS else "any"
        return self._refilter()

    @rx.event
    def set_uploaded(self, value: str):
        self.uploaded = value if value in youtube.UPLOADED else "any"
        return self._refilter()

    @rx.event
    def toggle_cc(self):
        self.cc_only = not self.cc_only
        return self._refilter()

    @rx.event(background=True)
    async def run_search(self):
        async with self:
            query = self.query.strip()
            if not query:
                return
            self._search_seq += 1
            seq = self._search_seq
            self.searching = True
            self.search_error = ""
            if query != self.searched:
                self.preview_id = ""
            limit, sort, duration, uploaded, cc = self.limit, self.sort, self.duration, self.uploaded, self.cc_only
        try:
            found, more = await asyncio.to_thread(
                youtube.search, query, limit, sort=sort, duration=duration, uploaded=uploaded, cc_only=cc
            )
            error = ""
        except Exception as e:  # noqa: BLE001 - shown to the user
            logging.warning("Search for %r failed: %s", query, e)
            found, more, error = [], False, youtube.error_message(e)
        async with self:
            if seq != self._search_seq:
                return  # a newer search is on its way
            self.searching = False
            self.searched = query
            self.search_error = error
            if not error:
                self.results = [_result_row(r) for r in found]
                self.more = more and len(found) >= limit
            elif limit == youtube.PAGE_SIZE:
                self.results = []
                self.more = False

    @rx.event
    def toggle_preview(self, video_id: str):
        self.preview_id = "" if self.preview_id == video_id else video_id

    @rx.event
    def set_tab(self, tab: str):
        self.tab = tab if tab in ("search", "library") else "search"
        self.playing = ""
        self.confirm_delete = ""
        if self.tab == "library":
            self._refresh_library()

    # -- conversions -----------------------------------------------------------

    @rx.event
    async def convert(self, video_id: str):
        row = next((r for r in self.results if r["id"] == video_id), None)
        if row is None or row["live"]:
            return
        job = await asyncio.to_thread(
            jobs.manager().submit,
            {"id": row["id"], "title": row["title"], "channel": row["channel"], "duration": float(row["duration"] or 0)},
        )
        if job is None:
            self._refresh_library()
            return
        self._apply(*jobs.manager().snapshot())
        events: list = [FinderState.watch]
        if (await self.get_state(IntentPage)).is_active:
            events.append(intent_update({"event": "started", "id": job.video_id, "title": job.title}))
        return events

    @rx.event
    def cancel_job(self, job_id: str):
        jobs.manager().cancel(job_id)
        self._apply(*jobs.manager().snapshot())

    @rx.event
    def retry_job(self, job_id: str):
        jobs.manager().retry(job_id)
        self._apply(*jobs.manager().snapshot())
        return FinderState.watch

    @rx.event
    def dismiss_job(self, job_id: str):
        jobs.manager().dismiss(job_id)
        self._apply(*jobs.manager().snapshot())

    @rx.event
    def clear_finished(self):
        jobs.manager().clear_finished()
        self._apply(*jobs.manager().snapshot())

    def _loop_alive(self) -> bool:
        return time.time() - self._watch_beat < BEAT_SECONDS

    @rx.event(background=True)
    async def watch(self):
        """Follow the backend's jobs while any is running or waiting (one loop per page)."""
        async with self:
            if self._loop_alive():
                return
            self._watch_beat = time.time()
        try:
            while True:
                await asyncio.sleep(POLL_SECONDS)
                version, rows = jobs.manager().snapshot()
                news: list[dict[str, Any]] = []
                async with self:
                    self._watch_beat = time.time()
                    in_dialog = (await self.get_state(IntentPage)).is_active
                    if version != self._version:
                        news = self._apply(version, rows)
                    running = any(r["active"] for r in rows)
                    if not running:
                        self._watch_beat = 0.0
                if in_dialog:
                    for update in news:
                        yield intent_update(update)
                if not running:
                    return
        except Exception:  # noqa: BLE001 - the next tick starts a fresh loop
            logging.exception("Following the conversions failed")
            async with self:
                self._watch_beat = 0.0

    @rx.event
    async def tick(self):
        """The check every few seconds: jobs started on another page, or a loop that died."""
        version, rows = jobs.manager().snapshot()
        if version == self._version and (self._loop_alive() or not any(r["active"] for r in rows)):
            return
        news = self._apply(version, rows)
        events: list = []
        if news and (await self.get_state(IntentPage)).is_active:
            events.extend(intent_update(update) for update in news)
        if any(r["active"] for r in rows) and not self._loop_alive():
            events.append(FinderState.watch)
        return events

    # -- answering the caller ------------------------------------------------------

    @rx.event
    def use(self, ref: str, title: str, duration: str):
        """Hand one MP3 to the caller (its ``on_update`` gets ``event: pick``)."""
        if ref:
            return intent_update(pick_update(ref, title, duration))

    @rx.event
    def done(self):
        return IntentPage.finish({"refs": list(self.dialog_refs)})

    # -- library -------------------------------------------------------------------

    @rx.event
    def refresh_library(self):
        self._refresh_library()

    @rx.event
    def toggle_play(self, item: str):
        self.playing = "" if self.playing == item else item

    @rx.event
    def ask_delete(self, item: str):
        self.confirm_delete = item

    @rx.event
    def keep(self):
        self.confirm_delete = ""

    @rx.event
    async def delete_item(self, item: str):
        self.confirm_delete = ""
        if self.playing == item:
            self.playing = ""
        removed = await asyncio.to_thread(library.remove, item)
        self._refresh_library()
        if not removed:
            return rx.toast.error("That MP3 could not be deleted.")
