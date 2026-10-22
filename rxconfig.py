import os
from pathlib import Path

import reflex as rx
from reflex.plugins import SitemapPlugin

# tauri_shell_app/appsrc links back to this folder (the desktop shell bundles the app), so the dev
# reloader would see every session save in .states through it and restart the backend, which kills
# the conversions in progress.
_tauri = str(Path(__file__).resolve().parent / "tauri_shell_app")
_excluded = [p for p in os.environ.get("REFLEX_HOT_RELOAD_EXCLUDE_PATHS", "").split(":") if p]
if _tauri not in _excluded:
    os.environ["REFLEX_HOT_RELOAD_EXCLUDE_PATHS"] = ":".join([*_excluded, _tauri])

config = rx.Config(
    app_name="youtube_to_mp3_tool", 
    plugins=[
        rx.plugins.TailwindV3Plugin(
            config={
                "plugins": ["@tailwindcss/typography@0.5.20"],
                # Reflex 0.10 compiles memoized components into .web/app_components,
                # which the plugin's default content globs miss, so their classes
                # would never be generated.
                "content": [
                    "./app/**/*.{js,ts,jsx,tsx}",
                    "./utils/**/*.{js,ts,jsx,tsx}",
                    "./app_components/**/*.{js,ts,jsx,tsx}",
                ],
            },
        ),
        rx.plugins.RadixThemesPlugin(theme=rx.theme(appearance="light")),
    ],
    disable_plugins=[SitemapPlugin]
)
