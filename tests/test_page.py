"""What the page tells a caller's dialog, and the file routes."""

import json
import time

import pytest
from starlette.testclient import TestClient

from youtube_to_mp3_tool import state as finder
from youtube_to_mp3_tool.api import api
from youtube_to_mp3_tool.state import FinderState

from .test_jobs import FakeWorld, _video


def _row(**over):
    row = {"id": "j1", "video_id": "abcdefghij1", "title": "Song", "channel": "C", "duration": 70.5,
           "status": "done", "progress": 100.0, "percent": "100%", "detail": "", "error": "",
           "ref": "audio:youtube-to-mp3/yt-abcdefghij1", "active": False, "finished": time.time()}
    row.update(over)
    return row


def test_payloads():
    job = finder._job_row(_row())
    assert finder.ready_update(job) == {"event": "ready", "ref": "audio:youtube-to-mp3/yt-abcdefghij1",
                                        "id": "abcdefghij1", "title": "Song", "duration": 70.5}
    failed = finder._job_row(_row(status="failed", error="This video is private.", ref=""))
    assert finder.failed_update(failed) == {"event": "failed", "id": "abcdefghij1", "title": "Song",
                                            "error": "This video is private."}
    assert finder.pick_update("audio:x/y", "T", "12.5") == {"event": "pick", "ref": "audio:x/y", "title": "T",
                                                            "duration": 12.5}
    assert finder.pick_update("audio:x/y", "T", "")["duration"] == 0.0


def test_news_is_told_once_and_only_for_jobs_finishing_after_opening(audio_root):
    page = FinderState(_reflex_internal_init=True)
    page._opened_at = time.time() - 1
    old = _row(id="j0", video_id="abcdefghij0", finished=time.time() - 60)
    running = _row(id="j2", video_id="abcdefghij2", status="downloading", active=True, finished=0.0, ref="")
    news = page._apply(1, [running, old, _row()])
    assert [n["event"] for n in news] == ["ready"]
    assert page.dialog_refs == ["audio:youtube-to-mp3/yt-abcdefghij1"]
    assert page._apply(2, [running, old, _row()]) == []
    failed = _row(id="j3", video_id="abcdefghij3", status="failed", error="Nope", ref="")
    assert page._apply(3, [running, failed]) == [{"event": "failed", "id": "abcdefghij3", "title": "Song", "error": "Nope"}]


def test_result_rows_show_library_and_running_jobs(audio_root):
    page = FinderState(_reflex_internal_init=True)
    page.results = [finder._result_row({"id": v, "title": v, "channel": "C", "duration": 70.0, "views": 1500, "live": False})
                    for v in ("abcdefghij1", "abcdefghij2", "abcdefghij3")]
    page.library = [{"video_id": "abcdefghij1", "ref": "audio:youtube-to-mp3/yt-abcdefghij1", "duration": "70.1"}]
    page.jobs = [
        finder._job_row(_row(id="j2", video_id="abcdefghij2", status="converting", active=True, percent="80%", ref="")),
        # Converted, then deleted from the library: offered again.
        finder._job_row(_row(id="j3", video_id="abcdefghij3", status="done")),
    ]
    rows = {r["id"]: r for r in page.result_rows}
    assert rows["abcdefghij1"]["state"] == "library" and rows["abcdefghij1"]["seconds"] == "70.1"
    assert rows["abcdefghij2"]["busy"] == "1" and rows["abcdefghij2"]["percent"] == "80%"
    assert rows["abcdefghij3"]["state"] == "" and rows["abcdefghij3"]["ref"] == ""
    assert rows["abcdefghij3"]["views_text"] == "1.5K views" and rows["abcdefghij3"]["duration_text"] == "1:10"


@pytest.fixture
def saved(audio_root):
    m = FakeWorld().manager()
    m.submit(_video(1))
    assert m.wait(10)
    return audio_root


def test_file_route_serves_our_mp3_with_ranges(saved):
    client = TestClient(api)
    whole = client.get("/api/yt2mp3/file/yt-abcdefghij1")
    assert whole.status_code == 200 and whole.headers["content-type"] == "audio/mpeg"
    assert whole.content.startswith(b"ID3") and len(whole.content) == 1000
    part = client.get("/api/yt2mp3/file/yt-abcdefghij1", headers={"Range": "bytes=0-9"})
    assert part.status_code == 206 and len(part.content) == 10
    download = client.get("/api/yt2mp3/file/yt-abcdefghij1?download=1")
    assert "attachment" in download.headers["content-disposition"]
    assert client.get("/api/yt2mp3/thumb/yt-abcdefghij1").headers["content-type"] == "image/jpeg"
    assert client.get("/api/yt2mp3/file/yt-nothere0000").status_code == 404
    assert client.get("/api/yt2mp3/file/..%2F..%2Fetc").status_code == 404


def test_other_apps_items_are_not_served(saved):
    other = saved / "audio" / "by-app" / "someone-else" / "yt-abcdefghij9"
    (other / ".item").mkdir(parents=True)
    (other / "x.mp3").write_bytes(b"ID3")
    (other / ".item" / "manifest.json").write_text(json.dumps({"kind": "audio.file", "primary": "x.mp3"}))
    assert TestClient(api).get("/api/yt2mp3/file/yt-abcdefghij9").status_code == 404


def test_a_page_whose_loop_stopped_beating_gets_a_new_one():
    page = FinderState(_reflex_internal_init=True)
    assert not page._loop_alive()  # never started
    page._watch_beat = time.time()
    assert page._loop_alive()
    page._watch_beat = time.time() - finder.BEAT_SECONDS - 1  # e.g. the backend restarted under it
    assert not page._loop_alive()
