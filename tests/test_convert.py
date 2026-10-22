"""The real ffmpeg conversion (skipped where ffmpeg is missing)."""

import shutil
import subprocess
import threading

import pytest

from youtube_to_mp3_tool import convert
from youtube_to_mp3_tool.youtube import Cancelled

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="needs ffmpeg")


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.m4a"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=6", "-c:a", "aac", str(path)],
        check=True,
    )
    return path


def test_to_mp3_reports_progress_and_tags(source, tmp_path):
    target = tmp_path / "out.mp3.part"
    seen = []
    convert.to_mp3(str(source), str(target), 6.0, {"title": "Beep", "artist": "Test"}, seen.append, lambda: False)
    assert seen[-1] == 1.0 and len(seen) >= 2
    assert abs(convert.duration_of(str(target)) - 6.0) < 0.2
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=format_name:format_tags=title,artist",
                            "-of", "default=nw=1", str(target)], capture_output=True, text=True).stdout
    assert "format_name=mp3" in probe and "TAG:title=Beep" in probe and "TAG:artist=Test" in probe


def test_to_mp3_stops_when_cancelled(source, tmp_path):
    stop = threading.Event()
    stop.set()
    with pytest.raises(Cancelled):
        convert.to_mp3(str(source), str(tmp_path / "out.mp3.part"), 6.0, {}, lambda f: None, stop.is_set)


def test_to_mp3_explains_a_failure(tmp_path):
    bad = tmp_path / "bad.webm"
    bad.write_bytes(b"not audio")
    with pytest.raises(RuntimeError, match="ffmpeg could not convert"):
        convert.to_mp3(str(bad), str(tmp_path / "out.mp3.part"), 1.0, {}, lambda f: None, lambda: False)


def test_duration_of_a_missing_file_is_zero(tmp_path):
    assert convert.duration_of(str(tmp_path / "missing.mp3")) == 0.0
