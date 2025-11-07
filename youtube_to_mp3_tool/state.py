import logging

import reflex as rx
import yt_dlp

logging.basicConfig(level=logging.INFO)


class ConverterState(rx.State):
    """Manages the state for the YouTube to MP3 converter."""

    url: str = ""
    is_loading: bool = False
    error_message: str = ""
    converted_file_info: dict[str, str] = {}

    def set_url(self, url: str):
        """Set the YouTube URL."""
        self.url = url

    def clear_results(self):
        """Clear the conversion results."""
        self.error_message = ""
        self.converted_file_info = {}
        self.is_loading = False

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
                "outtmpl": {
                    "default": str(upload_dir / "%(title)s.%(ext)s")
                },
                "noplaylist": True,
                "quiet": False,  # Enable logging to see more details
                "no_warnings": False,
                "logger": logging.getLogger(__name__),
                "http_headers": {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                },
                "geo_bypass": True,
                # Additional options to handle YouTube anti-bot measures
                "extractor_retries": 3,
                "fragment_retries": 3,
                "retry_sleep_functions": {"http": lambda n: 0.5 * n},
                "sleep_interval": 1,
                "max_sleep_interval": 5,
                # Try to use different extraction methods
                "extract_flat": False,
                "writesubtitles": False,
                "writeautomaticsub": False,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # First, extract info without downloading
                info_dict = ydl.extract_info(self.url, download=False)
                video_title = info_dict.get("title", "untitled_video")
                thumbnail_url = info_dict.get("thumbnail", "/placeholder.svg")
                
                # Clean the title for filename
                safe_title = "".join(
                    [c for c in video_title if c.isalnum() or c in (" ", "-", "_")]
                ).strip()
                
                # Fallback if title is too cleaned
                if not safe_title:
                    safe_title = f"video_{info_dict.get('id', 'unknown')}"
                
                output_filename = f"{safe_title}.mp3"
                output_path = upload_dir / output_filename
                
                # Create a new ydl instance for download with specific output path
                download_opts = ydl_opts.copy()
                download_opts["outtmpl"]["default"] = str(output_path.with_suffix('.%(ext)s'))
                
                with yt_dlp.YoutubeDL(download_opts) as download_ydl:
                    try:
                        # Try to download
                        download_ydl.download([self.url])
                    except yt_dlp.utils.DownloadError as download_error:
                        # If download fails, try with different format
                        if "empty" in str(download_error).lower():
                            # Try with a different format selection
                            download_opts["format"] = "worst[ext=mp4]/worst"
                            with yt_dlp.YoutubeDL(download_opts) as retry_ydl:
                                retry_ydl.download([self.url])
                        else:
                            raise download_error
            async with self:
                self.converted_file_info = {
                    "title": video_title,
                    "filename": output_filename,
                    "thumbnail": thumbnail_url,
                }
                self.is_loading = False
                self.url = ""
            yield rx.toast.success(f"Successfully converted: {video_title}", duration=5000)
        except yt_dlp.utils.DownloadError as e:
            logging.exception(f"Download Error: {e}")
            error_str = str(e).lower()
            async with self:
                if "sign in to confirm you're not a bot" in error_str or "authentication" in error_str:
                    self.error_message = (
                        "This video is protected and requires authentication. Please try a different video."
                    )
                elif "signature extraction failed" in error_str or "empty" in error_str:
                    self.error_message = (
                        "Failed to extract video data. This might be due to YouTube's anti-bot protection. "
                        "Please try again later or with a different video."
                    )
                elif "unavailable" in error_str or "private" in error_str:
                    self.error_message = (
                        "This video is unavailable, private, or has been removed."
                    )
                elif "copyright" in error_str:
                    self.error_message = (
                        "This video is protected by copyright and cannot be downloaded."
                    )
                else:
                    self.error_message = f"Download failed: {str(e)[:100]}{'...' if len(str(e)) > 100 else ''}"
                self.is_loading = False
            yield rx.toast.error("Conversion failed.", duration=5000)
        except Exception as e:
            logging.exception(f"An unexpected error occurred: {e}")
            async with self:
                self.error_message = "An unexpected error occurred. Please try again later."
                self.is_loading = False
            yield rx.toast.error("An unexpected error occurred.", duration=5000)
