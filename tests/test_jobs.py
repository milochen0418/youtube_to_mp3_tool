"""Conversions: publishing into the collection, running several at once, cancel, retry (no network, no ffmpeg)."""

import json
import threading
import time
from pathlib import Path

import pytest

from youtube_to_mp3_tool import library
from youtube_to_mp3_tool.jobs import JobManager
from youtube_to_mp3_tool.youtube import Cancelled

JPEG = b"\xff\xd8\xff\xe0" + b"\0" * 200


class FakeWorld:
    """yt-dlp, ffmpeg, the thumbnail and ffprobe, with a gate to hold downloads."""

    def __init__(self, hold: bool = False, fail: str = ""):
        self.gate = threading.Event()
        if not hold:
            self.gate.set()
        self.fail = fail
        self.running = 0
        self.most = 0
        self.lock = threading.Lock()

    def download(self, video_id, folder, on_details, on_progress, cancelled):
        on_details({"title": f"Song {video_id} / live", "channel": "The Key of Life",
                    "channel_url": "https://www.youtube.com/channel/UC1", "duration": 70,
                    "license": "Creative Commons Attribution license (reuse allowed)", "upload_date": "20230504"})
        with self.lock:
            self.running += 1
            self.most = max(self.most, self.running)
        try:
            while not self.gate.wait(0.01):
                if cancelled():
                    raise Cancelled()
            if self.fail:
                raise RuntimeError(self.fail)
            on_progress(500, 1000, 100)
            on_progress(1000, 1000, 100)
            path = Path(folder) / "source.webm"
            path.write_bytes(b"opus" * 100)
            return str(path)
        finally:
            with self.lock:
                self.running -= 1

    def convert(self, source, target, duration, tags, on_progress, cancelled):
        assert target.endswith(".mp3.part")
        assert tags["artist"] == "The Key of Life"
        on_progress(0.5)
        Path(target).write_bytes(b"ID3" + b"\0" * 997)
        on_progress(1.0)

    def manager(self, workers=3):
        return JobManager(workers=workers, download=self.download, converter=self.convert,
                          thumbnail=lambda vid: JPEG, probe=lambda path: 70.123)


def _video(n: int) -> dict:
    return {"id": f"abcdefghij{n}", "title": f"Song {n}", "channel": "C", "duration": 70}


def _status(m: JobManager) -> dict:
    return {row["video_id"]: row["status"] for row in m.snapshot()[1]}


def test_a_job_publishes_one_mp3_item(audio_root):
    m = FakeWorld().manager()
    job = m.submit(_video(1))
    assert m.wait(10)
    row = m.snapshot()[1][0]
    assert row["status"] == "done" and row["progress"] == 100.0
    assert row["ref"] == "audio:youtube-to-mp3/yt-abcdefghij1"
    assert row["duration"] == 70.123
    item = audio_root / "audio" / "by-app" / "youtube-to-mp3" / "yt-abcdefghij1"
    manifest = json.loads((item / ".item" / "manifest.json").read_text())
    assert manifest["kind"] == "audio.file"
    assert manifest["title"] == "Song abcdefghij1 / live"
    assert manifest["primary"] == "Song abcdefghij1 live.mp3"
    assert [f["path"] for f in manifest["files"]] == ["Song abcdefghij1 live.mp3"]
    assert manifest["source"] == "https://www.youtube.com/watch?v=abcdefghij1"
    assert manifest["meta"] == {
        "duration": 70.123, "format": "mp3", "youtube_id": "abcdefghij1", "channel": "The Key of Life",
        "channel_url": "https://www.youtube.com/channel/UC1",
        "license": "Creative Commons Attribution license (reuse allowed)", "upload_date": "20230504",
    }
    assert manifest["thumbnail"] == "thumbnail.jpg"
    assert (item / ".item" / "thumbnail.jpg").read_bytes() == JPEG
    assert not list((audio_root / "audio" / "by-app" / "youtube-to-mp3" / ".tmp").iterdir())
    assert job.title == "Song abcdefghij1 / live"


def test_at_most_n_run_at_once_and_the_rest_wait(audio_root):
    world = FakeWorld(hold=True)
    m = world.manager(workers=2)
    for n in range(4):
        m.submit(_video(n))
    deadline = time.time() + 5
    while world.running < 2 and time.time() < deadline:
        time.sleep(0.01)
    statuses = _status(m)
    assert sorted(statuses.values()).count("queued") == 2
    assert world.running == 2
    world.gate.set()
    assert m.wait(10)
    assert set(_status(m).values()) == {"done"}
    assert world.most == 2
    assert len(library.rows()) == 4


def test_the_same_video_twice_is_one_job_and_a_saved_one_is_not_queued(audio_root):
    world = FakeWorld(hold=True)
    m = world.manager()
    first = m.submit(_video(1))
    assert m.submit(_video(1)) is first
    world.gate.set()
    assert m.wait(10)
    assert m.submit(_video(1)) is None  # already in the library


def test_cancel_a_running_and_a_waiting_job(audio_root):
    world = FakeWorld(hold=True)
    m = world.manager(workers=1)
    running = m.submit(_video(1))
    waiting = m.submit(_video(2))
    deadline = time.time() + 5
    while world.running < 1 and time.time() < deadline:
        time.sleep(0.01)
    m.cancel(waiting.id)
    assert _status(m)["abcdefghij2"] == "cancelled"
    m.cancel(running.id)
    assert m.wait(10)
    assert _status(m)["abcdefghij1"] == "cancelled"
    own = audio_root / "audio" / "by-app" / "youtube-to-mp3"
    assert not (own / "yt-abcdefghij1").exists()
    assert not any((own / ".tmp").iterdir()) if (own / ".tmp").exists() else True


def test_a_failure_is_shown_and_retry_finishes_it(audio_root):
    world = FakeWorld(fail="ERROR: unable to download video data: HTTP Error 403: Forbidden")
    m = world.manager()
    job = m.submit(_video(1))
    assert m.wait(10)
    row = m.snapshot()[1][0]
    assert row["status"] == "failed"
    assert row["error"].startswith("YouTube refused")
    world.fail = ""
    assert m.retry(job.id) is job
    assert m.wait(10)
    assert _status(m)["abcdefghij1"] == "done"


def test_dismiss_and_clear_finished(audio_root):
    m = FakeWorld().manager()
    a = m.submit(_video(1))
    m.submit(_video(2))
    assert m.wait(10)
    m.dismiss(a.id)
    assert list(_status(m)) == ["abcdefghij2"]
    m.clear_finished()
    assert m.snapshot()[1] == []


def test_library_rows_and_remove(audio_root):
    m = FakeWorld().manager()
    m.submit(_video(1))
    assert m.wait(10)
    rows = library.rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["item"] == "yt-abcdefghij1" and row["video_id"] == "abcdefghij1"
    assert row["duration_text"] == "1:10" and row["ref"] == "audio:youtube-to-mp3/yt-abcdefghij1"
    assert library.mp3_path("yt-abcdefghij1").name == "Song abcdefghij1 live.mp3"
    assert library.remove("yt-abcdefghij1") is True
    assert library.rows() == []
    assert library.remove("../../etc") is False


@pytest.mark.parametrize(
    "title, name",
    [
        ("Passacaglia - Handel/Halvorsen", "Passacaglia - Handel Halvorsen.mp3"),
        ("2025 全新放鬆心情溫暖英文歌曲 | folkpop", "2025 全新放鬆心情溫暖英文歌曲 folkpop.mp3"),
        ("line\nbreak\ttab", "line break tab.mp3"),
        ("--dash first", "dash first.mp3"),
        ("...", "audio.mp3"),
        ("", "audio.mp3"),
        ("x" * 300, "x" * 116 + ".mp3"),
    ],
)
def test_mp3_name(title, name):
    assert library.mp3_name(title) == name
    assert len(library.mp3_name(title)) <= library.FILENAME_MAX


def test_cancel_while_converting_leaves_nothing_behind(audio_root):
    world = FakeWorld()
    gate = threading.Event()

    def slow_convert(source, target, duration, tags, on_progress, cancelled):
        Path(target).write_bytes(b"ID3partial")
        while not gate.wait(0.01):
            if cancelled():
                raise Cancelled()

    m = JobManager(workers=1, download=world.download, converter=slow_convert,
                   thumbnail=lambda vid: JPEG, probe=lambda path: 1.0)
    job = m.submit(_video(1))
    deadline = time.time() + 5
    while _status(m)["abcdefghij1"] != "converting" and time.time() < deadline:
        time.sleep(0.01)
    m.cancel(job.id)
    assert m.wait(10)
    assert _status(m)["abcdefghij1"] == "cancelled"
    own = audio_root / "audio" / "by-app" / "youtube-to-mp3"
    assert not (own / "yt-abcdefghij1").exists()
    assert list((own / ".tmp").iterdir()) == []


def test_a_full_quota_fails_the_job_visibly(audio_root, monkeypatch):
    from reflex_ddns_auth.collections import QuotaExceeded

    real = library.audio

    def full():
        collection = real()

        def publish(*args, **kwargs):
            raise QuotaExceeded("youtube-to-mp3 may keep 10.0 MB in 'audio' on this host and has 10.0 MB")

        collection.publish = publish
        return collection

    monkeypatch.setattr(library, "audio", full)
    m = FakeWorld().manager()
    m.submit(_video(1))
    assert m.wait(10)
    row = m.snapshot()[1][0]
    assert row["status"] == "failed"
    assert row["error"].startswith("No room left in the audio collection")
