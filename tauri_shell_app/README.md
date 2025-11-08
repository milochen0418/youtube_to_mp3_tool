# Tauri + React + Typescript

This template should help get you started developing with Tauri, React and Typescript in Vite.

## Recommended IDE Setup

- [VS Code](https://code.visualstudio.com/) + [Tauri](https://marketplace.visualstudio.com/items?itemName=tauri-apps.tauri-vscode) + [rust-analyzer](https://marketplace.visualstudio.com/items?itemName=rust-lang.rust-analyzer)


## 基礎環境

- X Code command line tool 
   - xcode-select --install
- rustc & cargo 
   - curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
      - rustc --version
      - cargo --version 
- node 
   - brew install node 
      - node --version
      - npm --version 


   

# Example of tauri_shell_app for spanish_audio_transcription

A Tauri (Rust + WebView) shell that runs the `spanish_audio_transcription` Reflex app as a native macOS desktop app.

- When you run this shell, it will:
  1. Start a self-contained Python runtime (`tauri_embedded_python/`) that already has Reflex + your app code installed.
  2. Launch the Reflex backend/web server locally (via `run_reflex_server.py`).
  3. Open a native macOS window pointing to that local URL.
  4. Kill the backend automatically when you close the window.

Result: users get a clickable desktop app UI for audio transcription, without needing Poetry, Conda, or manual terminal steps.

---

## Repository layout (important)

From the repo root (`spanish_audio_transcription/`):

```text
spanish_audio_transcription/        <- root of the Reflex app project
├── spanish_audio_transcription/    <- your actual app code (states/, etc)
├── assets/
├── uploaded_files/
├── tauri_embedded_python/          <- self-contained Python runtime (generated, NOT committed)
└── tauri_shell_app/                <- this folder (the Tauri desktop shell)
    ├── appsrc -> ..                <- symlink back to repo root
    ├── tauri_embedded_python -> ../tauri_embedded_python
    ├── run_reflex_server.py        <- wrapper that boots Reflex and reports which port it bound
    ├── src-tauri/                  <- Rust / Tauri side (main.rs, etc.)
    ├── src/                        <- Tauri front-end bootstrap (React/Vite, mostly unused now)
    ├── public/
    ├── node_modules/               <- (ignored) frontend deps
    └── package.json
```


# Dev run

先確認這樣子能否執行 
```
./tauri_embedded_python/bin/python run_reflex_server.py
```
確保你的 tauri embedded python 是有能力正常執行起來一個 reflex 專案

然後再
npm install
npm run tauri dev
