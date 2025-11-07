import reflex as rx
import yt_dlp
import logging

logging.basicConfig(level=logging.INFO)


class ConverterState(rx.State):
    """Manages the state for the YouTube to MP3 converter."""

    url: str = ""
    is_loading: bool = False
    error_message: str = ""
    converted_file_info: dict[str, str] = {}

    @rx.event(background=True)
    async def convert_video(self):
        """
        Downloads the audio from a YouTube URL and converts it to an MP3 file.
        This runs as a background task.
        """
        if not self.url:
            async with self:
                self.error_message = "Please enter a YouTube URL."
            return
        async with self:
            self.is_loading = True
            self.error_message = ""
            self.converted_file_info = {}
        try:
            upload_dir = rx.get_upload_dir()
            upload_dir.mkdir(parents=True, exist_ok=True)
            ydl_opts = {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "outtmpl": str(upload_dir / "%(title)s.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "logger": logging.getLogger(__name__),
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                },
                "geo_bypass": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(self.url, download=False)
                video_title = info_dict.get("title", "untitled_video")
                thumbnail_url = info_dict.get("thumbnail", "/placeholder.svg")
                safe_title = "".join(
                    [
                        c
                        for c in video_title
                        if c.isalpha() or c.isdigit() or c in (" ", "-")
                    ]
                ).rstrip()
                output_filename = f"{safe_title}.mp3"
                output_path = upload_dir / output_filename
                ydl.params["outtmpl"] = str(output_path)
                ydl.download([self.url])
            async with self:
                self.converted_file_info = {
                    "title": video_title,
                    "filename": output_filename,
                    "thumbnail": thumbnail_url,
                }
                self.is_loading = False
                self.url = ""
            yield rx.toast.success(
                f"Successfully converted: {video_title}", duration=5000
            )
        except yt_dlp.utils.DownloadError as e:
            logging.exception(f"Download Error: {e}")
            error_str = str(e).lower()
            async with self:
                if (
                    "sign in to confirm you're not a bot" in error_str
                    or "authentication" in error_str
                ):
                    self.error_message = "This video is protected and cannot be converted. Please try a different video."
                else:
                    self.error_message = "Invalid YouTube URL or download failed. Please check the URL and try again."
                self.is_loading = False
            yield rx.toast.error("Conversion failed.", duration=5000)
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            async with self:
                self.error_message = (
                    "An unexpected error occurred. Please try again later."
                )
                self.is_loading = False
            yield rx.toast.error("An unexpected error occurred.", duration=5000)

    @rx.event
    def clear_results(self):
        """Clears the previous conversion results."""
        self.converted_file_info = {}
        self.error_message = ""