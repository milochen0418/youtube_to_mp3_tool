# YouTube to MP3 Tool

A Reflex web application for converting YouTube videos to MP3 format.

## Prerequisites

- Python 3.11 or higher
- [Poetry](https://python-poetry.org/docs/#installation) for dependency management
- FFmpeg (required by yt-dlp for audio conversion)

### Install FFmpeg

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install ffmpeg
```

**Windows:**
Download from [FFmpeg official website](https://ffmpeg.org/download.html)

## Setup

1. **Install dependencies:**
   ```bash
   poetry install
   ```

2. **Initialize Reflex (first time only):**
   ```bash
   poetry run reflex init
   ```

## Development

### Running the Application

**Development mode:**
```bash
poetry run reflex run
```

Or use VSCode Task: `Ctrl+Shift+P` → `Tasks: Run Task` → `Run Reflex App (Development)`

### Code Quality

**Format code:**
```bash
poetry run black .
```

**Sort imports:**
```bash
poetry run isort .
```

**Lint code:**
```bash
poetry run flake8 .
```

**Run all quality checks:**
```bash
poetry run bash -c "black . && isort . && flake8 ."
```

### Testing

**Run tests:**
```bash
poetry run pytest
```

## VSCode Integration

This project includes VSCode configuration with:

- **Tasks** (`Ctrl+Shift+P` → `Tasks: Run Task`):
  - Install Dependencies
  - Run Reflex App (Development) - Default build task
  - Build Reflex App (Production)
  - Initialize Reflex
  - Format Code (Black)
  - Sort Imports (isort)
  - Lint Code (Flake8)
  - Run Tests - Default test task
  - Code Quality Check (All)
  - Clean Reflex Cache

- **Launch Configurations** (`F5` or Debug panel):
  - Debug Reflex App
  - Debug Python File

- **Workspace Settings**:
  - Python interpreter set to Poetry virtual environment
  - Auto-formatting on save
  - Import sorting on save
  - Proper file exclusions for better performance

## Project Structure

```
youtube_to_mp3_tool/
├── .vscode/                 # VSCode configuration
│   ├── tasks.json          # Build and run tasks
│   ├── launch.json         # Debug configurations
│   └── settings.json       # Workspace settings
├── youtube_to_mp3_tool/    # Main application package
│   ├── __init__.py
│   ├── state.py           # Application state management
│   └── youtube_to_mp3_tool.py  # UI components
├── assets/                 # Static assets
├── pyproject.toml         # Poetry configuration and dependencies
├── rxconfig.py            # Reflex configuration
└── README.md              # This file
```

## Production Build

```bash
poetry run reflex export --frontend-only
```

## Cleaning Cache

If you encounter issues, try cleaning the Reflex cache:

```bash
poetry run reflex clean
```

## Contributing

1. Ensure code follows the style guidelines (use the provided tasks)
2. Run tests before submitting changes
3. All checks should pass: `poetry run bash -c "black . && isort . && flake8 . && pytest"`