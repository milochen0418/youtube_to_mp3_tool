"""YouTube to MP3: find music on YouTube, preview it, convert several at once into the shared audio library.

Pages:

- ``/``                    the finder on its own
- ``/intent/audio-find``   the same finder in another app's dialog (DDNS Intent ``audio.find``,
                           param ``q`` = words to search right away); see ``state`` for what it
                           tells the caller while it stays open
"""

import logging

import reflex as rx
from reflex_ddns_auth.intent import intent

from youtube_to_mp3_tool.api import api
from youtube_to_mp3_tool.components import finder_dialog, finder_page
from youtube_to_mp3_tool.state import FinderState
from youtube_to_mp3_tool.static_pages import serve_pages_without_slash_redirect

# The conversions' log lines (start, done, failed with the reason) in the backend log.
_log = logging.getLogger("youtube_to_mp3_tool")
if not _log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)
    _log.propagate = False

app = rx.App(
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
            rel="stylesheet",
        ),
    ],
    stylesheets=["/finder.css"],
    api_transformer=[api, serve_pages_without_slash_redirect],
)
app.add_page(finder_page, route="/", title="YouTube to MP3", on_load=FinderState.load)


@intent(
    app,
    action="audio.find",
    title="Find audio on YouTube",
    params={"q": str},
    on_open=FinderState.open_intent,
)
def find_audio_intent() -> rx.Component:
    return finder_dialog()
