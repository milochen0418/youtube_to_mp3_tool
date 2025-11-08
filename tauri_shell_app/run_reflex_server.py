#!/usr/bin/env python3
import subprocess, sys, re, os

def main():
    # 取得 tauri_shell_app 的「絕對路徑」
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # runtime_python 指向我們 symlink 進來的獨立 Python runtime
    runtime_python = os.path.join(base_dir, "tauri_embedded_python", "bin", "python")

    # Reflex 真正的專案根 (appsrc 是 symlink -> .. 也就是 spanish_audio_transcription 專案根)
    project_dir = os.path.join(base_dir, "appsrc")

    # Debug 用 (你可以先保留，之後要乾淨可以刪)
    # 方便你確認路徑是不是你想的
    sys.stderr.write(f"[debug] base_dir={base_dir}\n")
    sys.stderr.write(f"[debug] runtime_python={runtime_python}\n")
    sys.stderr.write(f"[debug] project_dir(cwd)={project_dir}\n")
    sys.stderr.flush()

    # 啟動 Reflex。
    # 重點：
    #   1. 用我們指定的 runtime_python
    #   2. 執行 python -m reflex run
    #   3. cwd=project_dir 讓 Reflex 看到 rxconfig.py、pages/、state/ 等
    child = subprocess.Popen(
        [
            runtime_python,
            "-m", "reflex", "run"
        ],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    frontend_url = None
    backend_url = None

    assert child.stdout is not None
    for line in child.stdout:
        # 把 Reflex 的 log 都轉到 stderr（讓 Tauri dev console 可看）
        sys.stderr.write(line)
        sys.stderr.flush()

        # 尋找 Reflex 印出的 "App running at: http://localhost:3001/"
        m = re.search(r"App running at:\s*(http://[^\s]+)", line)
        if m and frontend_url is None:
            frontend_url = m.group(1).strip()
            # 把 URL 丟到 stdout 第一行 -> Tauri main.rs 會讀這一行
            print(frontend_url, flush=True)

        # 尋找 Reflex 印出的 "Backend running at: http://0.0.0.0:8003"
        m_backend = re.search(r"Backend running at:\s*(http://[^\s]+)", line)
        if m_backend and backend_url is None:
            backend_url = m_backend.group(1).strip()
            # 把 backend URL 丟到 stdout 第二行給 Tauri
            print(backend_url, flush=True)

    child.wait()

if __name__ == "__main__":
    main()
