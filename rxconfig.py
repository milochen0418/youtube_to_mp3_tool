import reflex as rx

config = rx.Config(
    app_name="youtube_to_mp3_tool", 
    plugins=[rx.plugins.TailwindV3Plugin()],
    disable_plugins=["reflex.plugins.sitemap.SitemapPlugin"]
)
