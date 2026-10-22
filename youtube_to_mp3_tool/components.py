"""The finder's UI: search bar and filters, results with preview, conversions, library, PIP panel."""

from __future__ import annotations

import reflex as rx
from reflex_ddns_auth.intent import IntentPage

from youtube_to_mp3_tool.api import file_url, thumb_url
from youtube_to_mp3_tool.state import FinderState

TICK_BUTTON_ID = "yt2mp3-tick"
# Checks every few seconds for conversions started on another page, or a following loop that
# died (the loop that follows running ones lives in the backend, see FinderState.watch).
TICK_JS = f"""(() => {{
  if (window.__yt2mp3Tick) return;
  window.__yt2mp3Tick = setInterval(() => {{
    const b = document.getElementById("{TICK_BUTTON_ID}");
    if (b) b.click();
  }}, 4000);
}})()"""

_BUTTON = "inline-flex items-center justify-center gap-1.5 rounded-md text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
_PRIMARY = _BUTTON + " bg-indigo-600 px-3 py-1.5 text-white hover:bg-indigo-500"
_SECONDARY = _BUTTON + " border border-neutral-700 bg-neutral-800 px-3 py-1.5 text-neutral-200 hover:bg-neutral-700"
_GHOST = _BUTTON + " px-2 py-1 text-neutral-400 hover:bg-neutral-800 hover:text-neutral-100"
_SELECT = (
    "rounded-md border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-xs text-neutral-200 "
    "focus:border-indigo-500 focus:outline-none"
)

STATUS_LABEL = {
    "queued": "Waiting",
    "fetching": "Starting",
    "downloading": "Downloading",
    "converting": "Converting",
    "saving": "Saving",
    "done": "Saved",
    "failed": "Failed",
    "cancelled": "Cancelled",
}
STATUS_BAR = {
    "queued": "bg-neutral-500",
    "fetching": "bg-sky-500",
    "downloading": "bg-sky-500",
    "converting": "bg-violet-500",
    "saving": "bg-violet-500",
    "done": "bg-emerald-500",
    "failed": "bg-red-500",
    "cancelled": "bg-neutral-600",
}
STATUS_TEXT = {
    "done": "text-emerald-400",
    "failed": "text-red-400",
    "cancelled": "text-neutral-500",
}


def _label(status: rx.Var) -> rx.Var:
    return rx.match(status, *STATUS_LABEL.items(), "")


def _bar_color(status: rx.Var) -> rx.Var:
    return rx.match(status, *STATUS_BAR.items(), "bg-sky-500")


def _status_color(status: rx.Var) -> rx.Var:
    return rx.match(status, *STATUS_TEXT.items(), "text-sky-300")


def in_dialog() -> rx.Var:
    return IntentPage.is_active


# -- search --------------------------------------------------------------------


def _select(value: rx.Var, on_change, options: list[tuple[str, str]], label: str) -> rx.Component:
    return rx.el.label(
        rx.el.span(label, class_name="sr-only"),
        rx.el.select(
            *[rx.el.option(text, value=key) for key, text in options],
            value=value,
            on_change=on_change,
            class_name=_SELECT,
            aria_label=label,
        ),
    )


def search_bar() -> rx.Component:
    return rx.el.div(
        rx.el.form(
            rx.el.div(
                rx.icon("search", class_name="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-500"),
                rx.el.input(
                    name="q",
                    type="search",
                    default_value=FinderState.query,
                    on_change=FinderState.set_query,
                    placeholder="Search YouTube or paste a link",
                    auto_complete="off",
                    class_name=(
                        "w-full rounded-lg border border-neutral-700 bg-neutral-900 py-2.5 pl-9 pr-3 text-sm "
                        "text-neutral-100 placeholder:text-neutral-500 focus:border-indigo-500 focus:outline-none"
                    ),
                ),
                class_name="relative flex-1",
            ),
            rx.el.button(
                rx.cond(FinderState.searching, rx.spinner(size="1"), rx.icon("search", class_name="h-4 w-4")),
                rx.el.span("Search"),
                type="submit",
                disabled=FinderState.searching,
                class_name=_BUTTON + " bg-red-600 px-4 py-2.5 text-sm text-white hover:bg-red-500",
            ),
            on_submit=FinderState.submit_search,
            reset_on_submit=False,
            class_name="flex items-center gap-2",
        ),
        rx.el.div(
            _select(
                FinderState.duration,
                FinderState.set_duration,
                [("any", "Any length"), ("short", "Under 4 minutes"), ("medium", "4–20 minutes"), ("long", "Over 20 minutes")],
                "Length",
            ),
            _select(
                FinderState.uploaded,
                FinderState.set_uploaded,
                [("any", "Any time"), ("week", "This week"), ("month", "This month"), ("year", "This year")],
                "Uploaded",
            ),
            _select(
                FinderState.sort,
                FinderState.set_sort,
                [("relevance", "Relevance"), ("views", "Most viewed")],
                "Order",
            ),
            rx.el.button(
                rx.cond(FinderState.cc_only, rx.icon("square-check", class_name="h-3.5 w-3.5"), rx.icon("square", class_name="h-3.5 w-3.5")),
                "Creative Commons only",
                on_click=FinderState.toggle_cc,
                type="button",
                title="Only videos their owners licensed for reuse (CC BY): credit the channel when you use them",
                class_name=rx.cond(
                    FinderState.cc_only,
                    _BUTTON + " border border-emerald-600 bg-emerald-900/40 px-2.5 py-1.5 text-emerald-300",
                    _BUTTON + " border border-neutral-700 bg-neutral-900 px-2.5 py-1.5 text-neutral-300 hover:bg-neutral-800",
                ),
            ),
            class_name="mt-2 flex flex-wrap items-center gap-2",
        ),
    )


def tabs() -> rx.Component:
    def tab(key: str, label) -> rx.Component:
        return rx.el.button(
            label,
            on_click=FinderState.set_tab(key),
            type="button",
            class_name=rx.cond(
                FinderState.tab == key,
                "border-b-2 border-red-500 px-1 pb-2 text-sm font-semibold text-neutral-100",
                "border-b-2 border-transparent px-1 pb-2 text-sm font-medium text-neutral-400 hover:text-neutral-200",
            ),
        )

    return rx.el.div(
        tab("search", "Search"),
        tab("library", rx.el.span("Library ", rx.el.span(FinderState.library.length(), class_name="text-neutral-500"))),
        class_name="mt-3 flex gap-5",
    )


# -- conversions ---------------------------------------------------------------


def _bar(job: rx.Var, height: str = "h-1.5") -> rx.Component:
    return rx.el.div(
        rx.cond(
            job["status"] == "queued",
            rx.el.div(class_name="yt-wait h-full w-1/3 rounded-full bg-neutral-500"),
            rx.el.div(
                class_name=_bar_color(job["status"]).to(str) + " h-full rounded-full transition-all duration-300",
                style={"width": job["progress"] + "%"},
            ),
        ),
        class_name=f"{height} w-full overflow-hidden rounded-full bg-neutral-800",
    )


def job_row(job: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.p(job["title"], class_name="truncate text-sm font-medium text-neutral-100", title=job["title"]),
                rx.el.p(
                    rx.el.span(_label(job["status"]), class_name=_status_color(job["status"]).to(str) + " font-medium"),
                    rx.cond(job["active"] != "", rx.el.span(" · " + job["percent"])),
                    rx.cond(job["error"] != "", rx.el.span(" · " + job["error"]), rx.el.span(rx.cond(job["detail"] != "", " · " + job["detail"], ""))),
                    class_name="truncate text-[11px] text-neutral-400",
                    title=rx.cond(job["error"] != "", job["error"], job["detail"]),
                ),
                class_name="min-w-0 flex-1",
            ),
            rx.el.div(
                rx.cond(
                    job["active"] != "",
                    rx.el.button("Cancel", on_click=FinderState.cancel_job(job["id"]), type="button", class_name=_GHOST),
                ),
                rx.cond(
                    (job["status"] == "failed") | (job["status"] == "cancelled"),
                    rx.el.button(
                        rx.icon("rotate-cw", class_name="h-3.5 w-3.5"), "Retry",
                        on_click=FinderState.retry_job(job["id"]), type="button", class_name=_SECONDARY,
                    ),
                ),
                rx.cond(
                    (job["status"] == "done") & in_dialog(),
                    rx.el.button(
                        rx.icon("plus", class_name="h-3.5 w-3.5"), "Use",
                        on_click=FinderState.use(job["ref"], job["title"], job["duration"]),
                        type="button", class_name=_PRIMARY,
                        title="Put it on the mixer's timeline",
                    ),
                ),
                rx.cond(
                    job["active"] == "",
                    rx.el.button(
                        rx.icon("x", class_name="h-3.5 w-3.5"),
                        on_click=FinderState.dismiss_job(job["id"]),
                        type="button", class_name=_GHOST, title="Remove from this list", aria_label="Dismiss",
                    ),
                ),
                class_name="flex shrink-0 items-center gap-1",
            ),
            class_name="flex items-center gap-3",
        ),
        _bar(job),
        class_name="flex flex-col gap-1.5 py-2",
        custom_attrs={"data-job": job["video_id"], "data-status": job["status"]},
    )


def jobs_panel() -> rx.Component:
    return rx.cond(
        FinderState.jobs.length() > 0,
        rx.el.section(
            rx.el.div(
                rx.el.h2(
                    "Conversions",
                    rx.el.span(
                        rx.cond(FinderState.active_count > 0, f" · {FinderState.active_count} running", ""),
                        class_name="font-normal text-neutral-400",
                    ),
                    class_name="text-xs font-semibold uppercase tracking-wider text-neutral-300",
                ),
                rx.cond(
                    FinderState.finished_count > 0,
                    rx.el.button("Clear finished", on_click=FinderState.clear_finished, type="button", class_name=_GHOST),
                ),
                class_name="flex items-center justify-between",
            ),
            rx.el.div(
                rx.foreach(FinderState.jobs, job_row),
                class_name="max-h-64 divide-y divide-neutral-800 overflow-y-auto",
            ),
            class_name="mt-4 rounded-xl border border-neutral-800 bg-neutral-900/70 px-4 py-3",
            id="conversions",
        ),
    )


# -- results ---------------------------------------------------------------------


def _row_action(row: rx.Var) -> rx.Component:
    return rx.cond(
        (row["state"] == "library") | (row["state"] == "done"),
        rx.el.div(
            rx.el.span(rx.icon("check", class_name="h-3.5 w-3.5"), "In library", class_name="inline-flex items-center gap-1 text-xs font-medium text-emerald-400"),
            rx.cond(
                in_dialog() & (row["ref"] != ""),
                rx.el.button(
                    rx.icon("plus", class_name="h-3.5 w-3.5"), "Use",
                    on_click=FinderState.use(row["ref"], row["title"], row["seconds"]),
                    type="button", class_name=_PRIMARY, title="Put it on the mixer's timeline",
                ),
            ),
            class_name="flex items-center gap-2",
        ),
        rx.cond(
            row["busy"] != "",
            rx.el.div(
                rx.el.span(rx.spinner(size="1"), "Converting ", row["percent"], class_name="inline-flex items-center gap-1.5 text-xs font-medium text-sky-300"),
                rx.el.button("Cancel", on_click=FinderState.cancel_job(row["job"]), type="button", class_name=_GHOST),
                class_name="flex items-center gap-1",
            ),
            rx.cond(
                row["state"] == "failed",
                rx.el.button(
                    rx.icon("rotate-cw", class_name="h-3.5 w-3.5"), "Retry",
                    on_click=FinderState.retry_job(row["job"]), type="button", class_name=_SECONDARY,
                ),
                rx.el.button(
                    rx.icon("music", class_name="h-3.5 w-3.5"),
                    rx.cond(row["live"] != "", "Live", "Convert to MP3"),
                    on_click=FinderState.convert(row["id"]),
                    disabled=row["live"] != "",
                    type="button",
                    class_name=_PRIMARY,
                    custom_attrs={"data-convert": row["id"]},
                ),
            ),
        ),
    )


def _preview(row: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.iframe(
                src="https://www.youtube-nocookie.com/embed/" + row["id"] + "?autoplay=1&rel=0&playsinline=1",
                title=row["title"],
                allow="autoplay; encrypted-media; picture-in-picture; fullscreen",
                referrer_policy="strict-origin-when-cross-origin",
                custom_attrs={"data-preview": row["id"]},
                class_name="absolute inset-0 h-full w-full",
            ),
            class_name="relative w-full overflow-hidden rounded-lg bg-black",
            style={"aspectRatio": "16 / 9"},
        ),
        rx.el.div(
            rx.el.a(
                rx.icon("external-link", class_name="h-3.5 w-3.5"), "Open on YouTube",
                href=row["watch"], target="_blank", rel="noopener noreferrer", class_name=_GHOST,
            ),
            rx.el.div(
                rx.el.button("Close preview", on_click=FinderState.toggle_preview(row["id"]), type="button", class_name=_GHOST),
                _row_action(row),
                class_name="flex items-center gap-2",
            ),
            class_name="mt-2 flex items-center justify-between gap-2",
        ),
        class_name="mt-3 w-full max-w-2xl",
    )


def result_row(row: rx.Var) -> rx.Component:
    previewing = FinderState.preview_id == row["id"]
    return rx.el.li(
        rx.el.div(
            rx.el.button(
                rx.el.img(src=row["thumb"], alt="", loading="lazy", class_name="h-full w-full object-cover"),
                rx.cond(
                    row["duration_text"] != "",
                    rx.el.span(
                        row["duration_text"],
                        class_name="absolute bottom-1 right-1 rounded bg-black/80 px-1 py-0.5 text-[10px] font-semibold text-white",
                    ),
                ),
                rx.el.span(
                    rx.cond(previewing, rx.icon("pause", class_name="h-5 w-5 text-white"), rx.icon("play", class_name="h-5 w-5 text-white")),
                    class_name="absolute inset-0 flex items-center justify-center bg-black/40 opacity-0 transition-opacity group-hover:opacity-100",
                ),
                on_click=FinderState.toggle_preview(row["id"]),
                type="button",
                title="Preview",
                class_name="group relative h-[72px] w-32 shrink-0 overflow-hidden rounded-md bg-neutral-800",
            ),
            rx.el.div(
                rx.el.button(
                    row["title"],
                    on_click=FinderState.toggle_preview(row["id"]),
                    type="button",
                    class_name="line-clamp-2 text-left text-sm font-medium text-neutral-100 hover:text-white",
                    title=row["title"],
                ),
                rx.el.p(
                    row["channel"],
                    rx.cond(row["views_text"] != "", " · " + row["views_text"], ""),
                    class_name="mt-0.5 truncate text-xs text-neutral-400",
                ),
                class_name="min-w-0 flex-1",
            ),
            rx.el.div(_row_action(row), class_name="shrink-0"),
            class_name="flex items-center gap-3",
        ),
        rx.cond(previewing, _preview(row)),
        class_name=rx.cond(
            previewing,
            "rounded-xl border border-neutral-700 bg-neutral-900 p-2",
            "rounded-xl border border-transparent p-2 hover:bg-neutral-900/60",
        ),
        custom_attrs={"data-video": row["id"], "data-state": row["state"]},
    )


def results() -> rx.Component:
    return rx.el.section(
        rx.cond(
            FinderState.search_error != "",
            rx.el.div(
                rx.icon("triangle-alert", class_name="h-4 w-4 shrink-0"),
                FinderState.search_error,
                class_name="mt-4 flex items-center gap-2 rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-sm text-red-300",
            ),
        ),
        rx.cond(
            (FinderState.results.length() == 0) & FinderState.searching,
            rx.el.div(
                *[
                    rx.el.div(
                        rx.el.div(class_name="h-[72px] w-32 animate-pulse rounded-md bg-neutral-800"),
                        rx.el.div(
                            rx.el.div(class_name="h-3 w-3/4 animate-pulse rounded bg-neutral-800"),
                            rx.el.div(class_name="mt-2 h-3 w-1/3 animate-pulse rounded bg-neutral-800"),
                            class_name="flex-1",
                        ),
                        class_name="flex items-center gap-3 p-2",
                    )
                    for _ in range(4)
                ],
                class_name="mt-3",
            ),
        ),
        rx.cond(
            (FinderState.results.length() == 0) & ~FinderState.searching & (FinderState.search_error == ""),
            rx.cond(
                FinderState.searched != "",
                rx.el.p("Nothing found. Try other words or fewer filters.", class_name="mt-6 text-center text-sm text-neutral-400"),
                rx.el.div(
                    rx.icon("music-2", class_name="mx-auto h-8 w-8 text-neutral-600"),
                    rx.el.p("Search like on YouTube, or paste a video or playlist link.", class_name="mt-3 text-sm text-neutral-300"),
                    rx.el.p(
                        "Click a result to listen to it first. Convert to MP3 saves it in the shared audio library, "
                        "where the Video Audio Mixer finds it. Several conversions run at the same time.",
                        class_name="mx-auto mt-1 max-w-md text-xs text-neutral-500",
                    ),
                    class_name="mt-10 text-center",
                ),
            ),
        ),
        rx.el.ul(rx.foreach(FinderState.result_rows, result_row), class_name="mt-3 flex flex-col gap-1"),
        rx.cond(
            FinderState.more & (FinderState.results.length() > 0),
            rx.el.div(
                rx.el.button(
                    rx.cond(FinderState.searching, rx.spinner(size="1"), rx.icon("chevrons-down", class_name="h-4 w-4")),
                    "More results",
                    on_click=FinderState.more_results,
                    disabled=FinderState.searching,
                    type="button",
                    class_name=_SECONDARY,
                ),
                class_name="mt-3 flex justify-center",
            ),
        ),
    )


# -- library ---------------------------------------------------------------------


def library_row(item: rx.Var) -> rx.Component:
    playing = FinderState.playing == item["item"]
    return rx.el.li(
        rx.el.div(
            rx.el.div(
                rx.el.img(src=thumb_url(item["item"]), alt="", loading="lazy", class_name="h-full w-full object-cover"),
                class_name="h-[54px] w-24 shrink-0 overflow-hidden rounded-md bg-neutral-800",
            ),
            rx.el.div(
                rx.el.p(item["title"], class_name="truncate text-sm font-medium text-neutral-100", title=item["title"]),
                rx.el.p(
                    rx.cond(item["channel"] != "", item["channel"] + " · ", ""),
                    item["duration_text"], " · ", item["size_text"],
                    rx.cond(
                        item["cc"] != "",
                        rx.el.span("CC BY", title=item["license"], class_name="ml-2 rounded bg-emerald-900/60 px-1 py-0.5 text-[10px] font-semibold text-emerald-300"),
                    ),
                    class_name="mt-0.5 truncate text-xs text-neutral-400",
                ),
                class_name="min-w-0 flex-1",
            ),
            rx.el.div(
                rx.cond(
                    FinderState.confirm_delete == item["item"],
                    rx.el.div(
                        rx.el.span("Delete this MP3?", class_name="text-xs text-red-300"),
                        rx.el.button("Delete", on_click=FinderState.delete_item(item["item"]), type="button",
                                     class_name=_BUTTON + " bg-red-600 px-2.5 py-1 text-white hover:bg-red-500"),
                        rx.el.button("Keep", on_click=FinderState.keep, type="button", class_name=_GHOST),
                        class_name="flex items-center gap-1.5",
                    ),
                    rx.el.div(
                        rx.el.button(
                            rx.cond(playing, rx.icon("square", class_name="h-3.5 w-3.5"), rx.icon("play", class_name="h-3.5 w-3.5")),
                            on_click=FinderState.toggle_play(item["item"]),
                            type="button", class_name=_GHOST, title=rx.cond(playing, "Stop", "Play"), aria_label="Play",
                        ),
                        rx.el.a(
                            rx.icon("download", class_name="h-3.5 w-3.5"),
                            href=file_url(item["item"], download=True),
                            class_name=_GHOST, title="Download the MP3",
                        ),
                        rx.cond(
                            in_dialog(),
                            rx.el.button(
                                rx.icon("plus", class_name="h-3.5 w-3.5"), "Use",
                                on_click=FinderState.use(item["ref"], item["title"], item["duration"]),
                                type="button", class_name=_PRIMARY, title="Put it on the mixer's timeline",
                            ),
                        ),
                        rx.el.button(
                            rx.icon("trash-2", class_name="h-3.5 w-3.5"),
                            on_click=FinderState.ask_delete(item["item"]),
                            type="button", class_name=_GHOST, title="Delete", aria_label="Delete",
                        ),
                        class_name="flex items-center gap-0.5",
                    ),
                ),
                class_name="shrink-0",
            ),
            class_name="flex items-center gap-3",
        ),
        rx.cond(
            playing,
            rx.el.audio(src=file_url(item["item"]), controls=True, auto_play=True, class_name="mt-2 h-8 w-full"),
        ),
        class_name="rounded-xl p-2 hover:bg-neutral-900/60",
        custom_attrs={"data-item": item["item"]},
    )


def library_list() -> rx.Component:
    return rx.el.section(
        rx.cond(
            FinderState.library.length() == 0,
            rx.el.p(
                "No MP3s yet. Search, then press Convert to MP3.",
                class_name="mt-10 text-center text-sm text-neutral-400",
            ),
            rx.el.ul(rx.foreach(FinderState.library, library_row), class_name="mt-3 flex flex-col gap-1"),
        ),
    )


# -- picture in picture ----------------------------------------------------------


def _pip_row(job: rx.Var) -> rx.Component:
    return rx.el.div(
        rx.el.div(
            rx.el.p(job["title"], class_name="min-w-0 flex-1 truncate text-[34px] font-semibold leading-tight text-white"),
            rx.el.p(
                rx.cond(job["active"] != "", job["percent"], _label(job["status"])),
                class_name=_status_color(job["status"]).to(str) + " shrink-0 text-[34px] font-bold tabular-nums",
            ),
            class_name="flex items-baseline gap-4",
        ),
        _bar(job, height="h-6"),
        class_name="flex flex-col gap-3",
    )


def pip_panel() -> rx.Component:
    """What a caller's picture-in-picture window shows (large print: it is scaled down ~2.5×)."""
    return rx.el.div(
        rx.el.div(
            rx.icon("music", class_name="h-12 w-12 shrink-0 text-red-500"),
            rx.el.p(FinderState.pip_title, class_name="text-[44px] font-bold leading-tight text-white"),
            class_name="flex items-center gap-4",
        ),
        rx.el.div(rx.foreach(FinderState.pip_jobs, _pip_row), class_name="mt-8 flex flex-col gap-8"),
        class_name="yt-pip bg-neutral-950 px-12 py-10 font-['Inter']",
    )


# -- pages -------------------------------------------------------------------------


def _ticker() -> rx.Component:
    return rx.el.button(
        id=TICK_BUTTON_ID,
        on_click=FinderState.tick,
        on_mount=rx.call_script(TICK_JS),
        class_name="yt-hidden",
        type="button",
        tab_index=-1,
    )


def _body() -> rx.Component:
    return rx.fragment(
        jobs_panel(),
        rx.cond(FinderState.tab == "library", library_list(), results()),
    )


def finder_page() -> rx.Component:
    """The app on its own: ``/``."""
    return rx.el.div(
        rx.el.main(
            rx.el.header(
                rx.el.div(
                    rx.icon("square-play", class_name="h-8 w-8 text-red-500"),
                    rx.el.div(
                        rx.el.h1("YouTube to MP3", class_name="text-xl font-bold tracking-tight"),
                        rx.el.p(
                            "Find music, listen first, convert several at once. The MP3s go to the shared audio library.",
                            class_name="text-xs text-neutral-400",
                        ),
                    ),
                    class_name="flex items-center gap-3",
                ),
                class_name="pb-4",
            ),
            rx.el.div(
                search_bar(),
                tabs(),
                class_name="sticky top-0 z-10 -mx-4 border-b border-neutral-800 bg-neutral-950/95 px-4 pt-3 backdrop-blur",
            ),
            _body(),
            class_name="mx-auto w-full max-w-4xl px-4 py-6",
        ),
        _ticker(),
        class_name="yt-main min-h-screen bg-neutral-950 font-['Inter'] text-neutral-100",
    )


def finder_dialog() -> rx.Component:
    """The app in another app's dialog: ``/intent/audio-find``. No min-height: the dialog follows its height."""
    return rx.fragment(
        rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.div(
                        rx.icon("square-play", class_name="h-5 w-5 text-red-500"),
                        rx.el.h1("Find audio on YouTube", class_name="text-sm font-semibold"),
                        class_name="flex items-center gap-2",
                    ),
                    rx.cond(
                        in_dialog(),
                        rx.el.button(
                            "Done",
                            rx.cond(FinderState.dialog_refs.length() > 0, " · " + FinderState.dialog_refs.length().to(str) + " saved", ""),
                            on_click=FinderState.done,
                            type="button",
                            class_name=_SECONDARY,
                            title="Close this window (conversions keep running here while it is minimized)",
                        ),
                    ),
                    # Room for the dialog's own buttons (picture in picture, minimize, close).
                    class_name="flex items-center justify-between gap-3 pr-[128px]",
                ),
                rx.el.div(search_bar(), class_name="mt-3"),
                tabs(),
                class_name="sticky top-0 z-10 border-b border-neutral-800 bg-neutral-950/95 px-4 pt-3 backdrop-blur",
            ),
            rx.el.div(_body(), class_name="px-4 pb-4"),
            _ticker(),
            class_name="yt-main bg-neutral-950 font-['Inter'] text-neutral-100",
        ),
        pip_panel(),
    )
