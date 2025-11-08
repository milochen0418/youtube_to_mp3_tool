use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio, Child};
use std::sync::{Arc, Mutex};
use std::path::PathBuf;

use tauri::{Manager, State, Url, WindowEvent};

#[derive(Clone)]
struct ReflexServerUrls {
    frontend_url: String,
    backend_url: String,
}

#[tauri::command]
fn get_reflex_server_urls(state: State<ReflexServerUrls>) -> (String, String) {
    (
        state.frontend_url.clone(),
        state.backend_url.clone(),
    )
}

/// 取得我們真正的專案根目錄 (tauri_shell_app/)
/// 邏輯：目前這支 main.rs 其實在 tauri_shell_app/src-tauri
///       我們取 current_exe() -> /.../tauri_shell_app/target/debug/tauri_shell_app
///       然後往上走到 src-tauri，再往上走一層
fn resolve_app_root() -> PathBuf {
    // 目前執行檔完整路徑，例如：
    // /Users/.../tauri_shell_app/target/debug/tauri_shell_app
    let exe_path = std::env::current_exe()
        .expect("failed to get current_exe");

    // target/debug/tauri_shell_app
    let target_dir = exe_path
        .parent()
        .expect("no parent for exe");

    // target/debug
    let debug_dir = target_dir
        .parent()
        .expect("no parent for target_dir");

    // target
    let target_parent = debug_dir
        .parent()
        .expect("no parent for debug_dir");

    // tauri_shell_app/
    let app_root = target_parent
        .parent()
        .expect("no parent for target/")
        .to_path_buf();

    app_root
}

/// 啟動我們的 Python wrapper (run_reflex_server.py)
/// 回傳：
/// - child_handle: Arc<Mutex<Option<Child>>> 用來之後 kill
/// - frontend_url: Reflex 真正跑起來的 URL，例如 http://localhost:3001
/// - backend_url: Reflex 後端 API 的 URL，例如 http://0.0.0.0:8003
fn spawn_reflex_wrapper() -> (Arc<Mutex<Option<Child>>>, String, String) {
    // 算出 tauri_shell_app/ 的絕對路徑
    let app_root = resolve_app_root();

    // 我們要在 tauri_shell_app/ 這一層執行
    // 那邊有:
    //   tauri_embedded_python/bin/python
    //   run_reflex_server.py
    //   appsrc (symlink 到你的 Reflex 專案)
    let mut child = Command::new("./tauri_embedded_python/bin/python")
        .arg("run_reflex_server.py")
        .stdout(Stdio::piped())   // run_reflex_server.py 第一行會印 URL
        .stderr(Stdio::piped())   // Reflex log 走 stderr (目前沒即時處理)
        .current_dir(&app_root)   // <── 這是關鍵
        .spawn()
        .expect("Failed to spawn run_reflex_server.py");

    // 從 stdout 讀第一行，把它當作 URL
    let stdout = child
        .stdout
        .take()
        .expect("No stdout from run_reflex_server.py");

    let mut reader = BufReader::new(stdout);

    let mut frontend_url: Option<String> = None;
    let mut backend_url: Option<String> = None;

    loop {
        let mut line = String::new();
        let bytes_read = reader
            .read_line(&mut line)
            .expect("Failed to read output from run_reflex_server.py");

        if bytes_read == 0 {
            panic!("run_reflex_server.py did not return Reflex URLs");
        }

        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        if frontend_url.is_none() {
            frontend_url = Some(trimmed.to_string());
            continue;
        }

        if backend_url.is_none() {
            backend_url = Some(trimmed.to_string());
        }

        if frontend_url.is_some() && backend_url.is_some() {
            break;
        }
    }

    let frontend_url = frontend_url.expect("frontend URL missing");
    let backend_url = backend_url.expect("backend URL missing");

    // 把 child 包起來供後面 kill
    let child_handle = Arc::new(Mutex::new(Some(child)));

    (child_handle, frontend_url, backend_url)
}

fn main() {
    // 啟動 Reflex
    let (child_handle, frontend_url, backend_url) = spawn_reflex_wrapper();

    // 我們要把 child_handle 同時給 setup() 和 on_window_event()
    let child_for_setup = Arc::clone(&child_handle);
    let child_for_close = Arc::clone(&child_handle);
    let frontend_for_setup = frontend_url.clone();

    tauri::Builder::default()
        .manage(ReflexServerUrls {
            frontend_url,
            backend_url,
        })
        .invoke_handler(tauri::generate_handler![get_reflex_server_urls])
        // setup: 視窗建立後導向 Reflex 給的 URL
        .setup(move |app| {
            // 取得 main 視窗 (Tauri v2 用 get_webview_window)
            let window = app
                .get_webview_window("main")
                .expect("cannot find main window");

            // 用 JS 直接讓 webview 跳轉到 Reflex 的網址
            let target_url = Url::parse(&frontend_for_setup)
                .expect("invalid Reflex frontend URL");

            window
                .navigate(target_url)
                .expect("failed to navigate webview to Reflex frontend");

            // 讓 child_for_setup 活著，避免 child_handle 在 setup 之後就被 drop
            let _keep_alive = child_for_setup;
            Ok(())
        })
        // 關視窗時，把 Reflex server 關掉
        .on_window_event(move |_window, event| {
            if let WindowEvent::CloseRequested { .. } = event {
                if let Ok(mut guard) = child_for_close.lock() {
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri app");
}
