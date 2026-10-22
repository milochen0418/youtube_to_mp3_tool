"""Search parameters, link detection and error messages (no network)."""

import base64

import pytest

from youtube_to_mp3_tool import youtube


@pytest.mark.parametrize(
    "filters, expected",
    [
        ({}, "EgIQAQ=="),  # videos only
        ({"duration": "short"}, "EgQQARgB"),  # checked against youtube.com: < 4 min
        ({"duration": "medium"}, "EgQQARgD"),
        ({"duration": "long"}, "EgQQARgC"),
        ({"duration": "short", "cc_only": True}, "EgYQARgBMAE="),
        ({"sort": "views"}, "CAMSAhAB"),
        ({"uploaded": "week"}, "EgQIAxAB"),
    ],
)
def test_search_params(filters, expected):
    assert youtube.search_params(**filters) == expected


def test_search_params_ignore_unknown_values():
    assert youtube.search_params(sort="nope", duration="nope", uploaded="nope") == "EgIQAQ=="


def test_search_url_encodes_the_query_and_filters():
    url = youtube.search_url("piano & rain", duration="short", cc_only=True)
    assert url.startswith("https://www.youtube.com/results?search_query=piano+%26+rain&sp=")
    sp = url.split("sp=")[1].replace("%3D", "=")
    assert base64.b64decode(sp) == b"\x12\x06\x10\x01\x18\x01\x30\x01"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("https://www.youtube.com/watch?v=FLPF4IUdIOw", ("video", "FLPF4IUdIOw")),
        ("youtube.com/watch?v=FLPF4IUdIOw&list=PL123", ("video", "FLPF4IUdIOw")),
        ("https://youtu.be/FLPF4IUdIOw?t=10", ("video", "FLPF4IUdIOw")),
        ("https://m.youtube.com/shorts/FLPF4IUdIOw", ("video", "FLPF4IUdIOw")),
        ("https://music.youtube.com/watch?v=FLPF4IUdIOw", ("video", "FLPF4IUdIOw")),
        ("https://www.youtube.com/playlist?list=PLabc", ("playlist", "https://www.youtube.com/playlist?list=PLabc")),
        ("piano music", None),
        ("https://example.com/watch?v=FLPF4IUdIOw", None),
        ("https://www.youtube.com/@SomeChannel", None),
    ],
)
def test_youtube_link(text, expected):
    assert youtube.youtube_link(text) == expected


def test_entries_keep_videos_only():
    video = {"_type": "url", "ie_key": "Youtube", "id": "FLPF4IUdIOw", "title": "T", "duration": 70,
             "channel": "C", "view_count": 10}
    channel = {"_type": "url", "ie_key": "YoutubeTab", "id": "UC_tiQphRqI1V1btEDTXsRMQ", "title": "C"}
    live = {"_type": "url", "ie_key": "Youtube", "id": "y6TZHLAzg5o", "title": "24/7", "duration": None}
    assert youtube._entry(video) == {"id": "FLPF4IUdIOw", "title": "T", "channel": "C", "duration": 70.0,
                                     "views": 10, "live": False}
    assert youtube._entry(channel) is None
    assert youtube._entry(live)["live"] is True


@pytest.mark.parametrize(
    "raw, starts",
    [
        ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", "YouTube wants a signed-in user"),
        ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "YouTube refused"),
        ("ERROR: [youtube] abcdefghijk: Private video", "This video is private"),
        ("ERROR: [youtube] abcdefghijk: Video unavailable", "This video is unavailable"),
        ("ERROR: [youtube] abcdefghijk: Something new happened", "Something new happened"),
    ],
)
def test_error_message(raw, starts):
    assert youtube.error_message(Exception(raw)).startswith(starts)
