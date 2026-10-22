# YouTube to MP3

Find music on YouTube the way you would on youtube.com, listen to it first, and convert it to MP3,
several at once. Every MP3 goes into the shared **audio library** (the Owned Collection `audio`),
where other apps such as the Video Audio Mixer pick it up. Other apps can also open this app as a
dialog (DDNS Intent `audio.find`), which keeps running in the background or as a small
picture-in-picture window while the MP3s are made.

## What it does

- **Search** like on YouTube, with its filters: length (under 4 min, 4–20 min, over 20 min),
  upload date (this week / month / year), order (relevance, most viewed) and
  **Creative Commons only** (videos their owners licensed for reuse; credit the channel).
  A pasted YouTube link shows that video; a playlist link shows its videos.
- **Preview**: click a result to play it in place (the YouTube player), then **Convert to MP3**.
- **Conversions** run in the backend, `YT2MP3_PARALLEL` at a time (default 3), the others wait in
  line. Each shows its stage and progress (downloading, converting, saving); cancel, retry, dismiss.
  They keep running when the page is closed, and every open page shows them.
- **Library**: this app's MP3s, to play, download or delete.

YouTube's search page no longer sorts by upload date, so "newest" is the upload-date filter instead.

## The audio library (Owned Collection `audio`)

One item per video, published only when complete (see re_ddns `docs/collections.md`):

```
<collections root>/audio/by-app/youtube-to-mp3/yt-<video id>/<title>.mp3   the payload: one MP3, the primary
<collections root>/audio/by-app/youtube-to-mp3/yt-<video id>/.item/        manifest + thumbnail (320×180 JPEG)
```

| | |
|---|---|
| kind | `audio.file` |
| ref | `audio:youtube-to-mp3/yt-<video id>` |
| title | the video's title |
| source | `https://www.youtube.com/watch?v=<video id>` |
| meta | `duration` (s, of the MP3), `format` (`mp3`), `youtube_id`, `channel`, `channel_url`, `license` (YouTube's licence text, `""` when standard), `upload_date` (YYYYMMDD) |

The MP3 is VBR ~190 kb/s (LAME `-q:a 2`) with ID3v2.3 title, artist (channel) and comment (the
video's link). In the App Store the catalog entry declares `{"collection": "audio", "access":
"contribute"}`; run on its own, the app writes to the same tree as owner `youtube-to-mp3`
(`DDNS_COLLECTIONS_ROOT`, else `/Users/Shared/re-ddns/collections` on macOS).

## The dialog other apps open: `audio.find`

```python
from reflex_ddns_auth.intent import Intent

rx.button("Find on YouTube", on_click=Intent.start(
    "youtube-to-mp3", "audio.find", keep_alive=True, single=True, label="YouTube → MP3",
    on_update=MyState.audio_news, on_result=MyState.audio_done, q="piano"))
```

`q` (optional) is searched right away. While the dialog is open (also minimized or as a
picture-in-picture window) the caller's `on_update` gets:

| `event` | when | data |
|---|---|---|
| `started` | a conversion was queued in this dialog | `id`, `title` |
| `ready` | an MP3 was saved (any conversion that finishes while the dialog is open) | `ref`, `id`, `title`, `duration` |
| `failed` | a conversion failed | `id`, `title`, `error` |
| `pick` | the user pressed **Use** on a saved MP3 | `ref`, `title`, `duration` |

**Done** answers the dialog: `on_result` gets `{"refs": [<refs saved while it was open>]}`.
In a picture-in-picture window (`<html data-intent-view="pip">`) the page shows only a
large-print progress panel, readable at that size.

## Settings

| Variable | Default | |
|---|---|---|
| `YT2MP3_PARALLEL` | `3` | conversions at the same time (1–8) |
| `YT2MP3_WORK_DIR` | system temp | where downloads wait to be converted |
| `DDNS_COLLECTIONS_ROOT`, `DDNS_APP_ID` | set by the App Store | the collection tree and our owner name |

## Development

Needs Python 3.11–3.15, [Poetry](https://python-poetry.org/), **ffmpeg** (`brew install ffmpeg`;
`apt-packages.txt` for the App Store) and a JavaScript runtime for YouTube's challenges: deno,
node 22+ or bun (the App Store image has node 22 and bun). `reflex-ddns-auth` is a path
dependency on `../reflex_ddns_auth`.

```bash
poetry install
# a private collection tree, so a test run never touches the real library:
DDNS_COLLECTIONS_ROOT=/tmp/collections DDNS_APP_ID=youtube-to-mp3 \
  poetry run reflex run
poetry run pytest
```

To try the dialog against a local caller, run with `DDNS_INTENT_TRUST_LOCALHOST=1` and open
`/intent/audio-find?_intent_id=t1&_intent_origin=<the caller's origin>` in an iframe.

Code: `youtube.py` (yt-dlp: search, details, download), `convert.py` (ffmpeg), `jobs.py` (the
conversions), `library.py` (the collection), `api.py` (`/api/yt2mp3/file/<item>` with Range
support, `/api/yt2mp3/thumb/<item>`), `state.py` + `components.py` (the page),
`static_pages.py` (keeps `/intent/audio-find` from redirecting in Reflex prod mode).

The `tauri_shell_app/` desktop wrapper is unchanged.
