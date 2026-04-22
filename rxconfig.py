import reflex as rx
from reflex.plugins import SitemapPlugin

config = rx.Config(
    app_name="youtube_to_mp3_tool", 
    plugins=[rx.plugins.TailwindV3Plugin()],
    disable_plugins=[SitemapPlugin]
)
