import reflex as rx

from youtube_to_mp3_tool.state import ConverterState


def loading_skeleton() -> rx.Component:
    """Displays a skeleton loader while the conversion is in progress."""
    return rx.el.div(
        rx.el.div(class_name="h-4 bg-gray-200 rounded-full w-48 mb-4 animate-pulse"),
        rx.el.div(class_name="h-4 bg-gray-200 rounded-full max-w-[360px] mb-2.5 animate-pulse"),
        rx.el.div(class_name="h-4 bg-gray-200 rounded-full mb-2.5 animate-pulse"),
        rx.el.div(class_name="h-10 bg-gray-200 rounded-lg w-full mt-6 animate-pulse"),
        class_name="w-full max-w-md mx-auto p-8 border border-gray-200 rounded-2xl shadow-lg bg-white",
    )


def result_card() -> rx.Component:
    """Displays the card with the converted MP3's information and download button."""
    return rx.el.div(
        rx.el.div(
            rx.el.div(
                rx.el.button(
                    rx.icon(tag="x", class_name="h-4 w-4"),
                    on_click=ConverterState.clear_results,
                    class_name="absolute top-4 right-4 text-gray-400 hover:text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-full p-1.5 transition-colors",
                ),
                rx.el.div(
                    rx.image(
                        src=ConverterState.converted_file_info.get("thumbnail", "/placeholder.svg"),
                        alt=ConverterState.converted_file_info.get("title", "Video Thumbnail"),
                        class_name="w-24 h-24 object-cover rounded-lg shadow-md",
                    ),
                    rx.el.div(
                        rx.el.h3(
                            ConverterState.converted_file_info.get("title", "Unknown Title"),
                            class_name="text-lg font-semibold text-gray-800 line-clamp-2",
                        ),
                        rx.el.p(
                            "Conversion successful!",
                            class_name="text-sm text-green-600 font-medium mt-1",
                        ),
                        class_name="flex-1 min-w-0 ml-4",
                    ),
                    class_name="flex items-center",
                ),
                rx.el.button(
                    rx.icon(tag="download", class_name="mr-2 h-5 w-5"),
                    "Download MP3",
                    on_click=rx.download(
                        url=rx.get_upload_url(ConverterState.converted_file_info.get("filename", "")),
                        filename=ConverterState.converted_file_info.get("filename", "audio.mp3"),
                    ),
                    class_name="w-full mt-6 flex items-center justify-center px-4 py-3 bg-gradient-to-r from-blue-500 to-blue-600 text-white font-semibold rounded-lg shadow-md hover:shadow-lg hover:from-blue-600 hover:to-blue-700 transition-all duration-300 transform hover:scale-[1.02]",
                ),
                class_name="relative w-full max-w-md mx-auto p-8 border border-gray-200 rounded-2xl shadow-lg bg-white transition-opacity duration-500",
            ),
            class_name="mt-8",
        ),
        class_name="w-full",
    )


def index() -> rx.Component:
    """The main page of the YouTube to MP3 converter app."""
    return rx.el.main(
        rx.el.div(
            rx.el.div(
                rx.icon(tag="square-play", class_name="h-12 w-12 text-blue-500"),
                rx.el.h1(
                    "YouTube to MP3 Converter",
                    class_name="text-3xl sm:text-4xl font-bold text-gray-800 mt-4 text-center",
                ),
                rx.el.p(
                    "Paste a YouTube video URL below to convert it into an MP3 file.",
                    class_name="text-gray-500 mt-2 text-center max-w-md",
                ),
                class_name="flex flex-col items-center",
            ),
            rx.el.div(
                rx.el.div(
                    rx.el.input(
                        placeholder="https://www.youtube.com/watch?v=...",
                        on_change=ConverterState.set_url,
                        class_name="w-full px-4 py-3 text-lg bg-white border-2 border-gray-200 rounded-lg focus:ring-2 focus:ring-blue-400 focus:border-transparent transition-all",
                        default_value=ConverterState.url,
                    ),
                    rx.el.button(
                        rx.cond(
                            ConverterState.is_loading,
                            rx.spinner(class_name="h-6 w-6 text-white"),
                            rx.el.span("Convert"),
                        ),
                        on_click=ConverterState.convert_video,
                        disabled=ConverterState.is_loading,
                        class_name="w-full sm:w-auto px-8 py-3 bg-gradient-to-r from-blue-500 to-indigo-600 text-white text-lg font-semibold rounded-lg shadow-md hover:shadow-lg hover:from-blue-600 hover:to-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-300",
                    ),
                    class_name="flex flex-col sm:flex-row items-center gap-4",
                ),
                rx.cond(
                    ConverterState.error_message != "",
                    rx.el.div(
                        rx.icon(
                            tag="flag_triangle_right",
                            class_name="h-5 w-5 text-red-600 mr-2",
                        ),
                        ConverterState.error_message,
                        class_name="mt-4 flex items-center text-red-600 bg-red-100 p-3 rounded-lg",
                    ),
                    None,
                ),
                class_name="w-full max-w-2xl mt-8",
            ),
            rx.cond(
                ConverterState.is_loading,
                loading_skeleton(),
                rx.cond(
                    ConverterState.converted_file_info.keys().length() > 0,
                    result_card(),
                    None,
                ),
            ),
            class_name="flex flex-col items-center justify-center min-h-screen p-4 sm:p-6 bg-gray-50",
        ),
        class_name="font-['Inter'] bg-white",
    )


app = rx.App(
    head_components=[
        rx.el.link(rel="preconnect", href="https://fonts.googleapis.com"),
        rx.el.link(rel="preconnect", href="https://fonts.gstatic.com", cross_origin=""),
        rx.el.link(
            href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap",
            rel="stylesheet",
        ),
    ],
)
app.add_page(index)
