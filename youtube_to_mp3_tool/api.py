"""Backend routes for the library's files, under ``/api`` (the re-ddns nginx sends ``/api`` to the backend).

    GET /api/yt2mp3/file/<item id>[?download=1]   one of our MP3s (Range requests work, so it seeks)
    GET /api/yt2mp3/thumb/<item id>               its preview picture

Only this app's own items of the ``audio`` collection are served.
"""

from __future__ import annotations

import asyncio

import reflex as rx
from reflex.constants import Dirs
from reflex.utils.imports import ImportVar
from reflex.vars import VarData
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

from youtube_to_mp3_tool import library

FILE_PATH = "/api/yt2mp3/file"
THUMB_PATH = "/api/yt2mp3/thumb"

_THUMB_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}

# The backend's origin as the page sees it: the frontend's own origin behind
# nginx and in prod, the backend port in a local dev run.
backend_origin = rx.Var(
    _js_expr="getBackendURL(env.UPLOAD).origin",
    _var_data=VarData(
        imports={
            f"$/{Dirs.STATE_PATH}": "getBackendURL",
            "$/env.json": ImportVar(tag="env", is_default=True),
        }
    ),
).to(str)


def file_url(item: rx.Var | str, download: bool = False) -> rx.Var:
    return rx.Var.create(f"{backend_origin}{FILE_PATH}/{item}" + ("?download=1" if download else ""))


def thumb_url(item: rx.Var | str) -> rx.Var:
    return rx.Var.create(f"{backend_origin}{THUMB_PATH}/{item}")


async def mp3_file(request: Request) -> Response:
    path = await asyncio.to_thread(library.mp3_path, request.path_params["item"])
    if path is None:
        return Response(status_code=404)
    if request.query_params.get("download") == "1":
        return FileResponse(path, media_type="audio/mpeg", filename=path.name)
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


async def thumbnail(request: Request) -> Response:
    path = await asyncio.to_thread(library.thumbnail_path, request.path_params["item"])
    if path is None:
        return Response(status_code=404)
    return FileResponse(
        path,
        media_type=_THUMB_TYPES.get(path.suffix, "application/octet-stream"),
        headers={"Cache-Control": "public, max-age=86400"},
    )


api = Starlette(
    routes=[
        Route(FILE_PATH + "/{item}", mp3_file, methods=["GET", "HEAD"]),
        Route(THUMB_PATH + "/{item}", thumbnail, methods=["GET", "HEAD"]),
    ]
)
