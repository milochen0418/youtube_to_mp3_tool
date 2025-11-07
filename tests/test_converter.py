"""
Basic tests for the YouTube to MP3 converter application.
"""

import pytest

from youtube_to_mp3_tool.state import ConverterState


class TestConverterState:
    """Test cases for the ConverterState class."""

    def test_initial_state(self):
        """Test that the initial state is properly set."""
        state = ConverterState()

        assert state.url == ""
        assert state.is_loading is False
        assert state.error_message == ""
        assert state.converted_file_info == {}

    def test_url_validation_empty_url(self):
        """Test URL validation with empty URL."""
        state = ConverterState()
        # Note: This test would require async testing setup for the actual
        # convert_video method. For now, we just test the initial state
        assert state.url == ""

    def test_state_properties(self):
        """Test that state properties can be set."""
        state = ConverterState()

        # Test setting URL
        state.url = "https://youtube.com/watch?v=test"
        assert state.url == "https://youtube.com/watch?v=test"

        # Test setting loading state
        state.is_loading = True
        assert state.is_loading is True

        # Test setting error message
        state.error_message = "Test error"
        assert state.error_message == "Test error"

        # Test setting converted file info
        state.converted_file_info = {"title": "Test Video"}
        assert state.converted_file_info == {"title": "Test Video"}

    def test_clear_results(self):
        """Test that clear_results method works correctly."""
        state = ConverterState()

        # Set some state
        state.url = "https://youtube.com/watch?v=test"
        state.error_message = "Some error"
        state.converted_file_info = {"title": "Test"}

        # Clear results
        state.clear_results()

        # Check that certain fields are cleared while URL remains
        # URL should remain unchanged
        assert state.url == "https://youtube.com/watch?v=test"
        assert state.error_message == ""
        assert state.converted_file_info == {}
        assert state.is_loading is False


def test_app_imports():
    """Test that all required modules can be imported."""
    try:
        import reflex as rx  # noqa: F401
        import yt_dlp  # noqa: F401

        from youtube_to_mp3_tool import state, youtube_to_mp3_tool  # noqa: F401
    except ImportError as e:
        pytest.fail(f"Failed to import required modules: {e}")


def test_reflex_config():
    """Test that Reflex configuration is properly set up."""
    try:
        import rxconfig

        assert hasattr(rxconfig, "config")
        assert rxconfig.config.app_name == "youtube_to_mp3_tool"
    except (ImportError, AttributeError) as e:
        pytest.fail(f"Reflex configuration not properly set up: {e}")
