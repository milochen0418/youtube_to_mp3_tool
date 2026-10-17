import reflex as rx
from reflex.plugins import SitemapPlugin

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
