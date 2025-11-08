# 1. 找出這個專案的 Poetry venv 路徑
POETRY_ENV_PATH="$(poetry env info --path)"

# 2. 取得這個專案實際使用的 python 執行檔路徑
POETRY_PYTHON="$(poetry run which python)"

# 3. 印出讓你眼睛確認一下 (可留可刪)
echo "Poetry venv path: $POETRY_ENV_PATH"
echo "Poetry python   : $POETRY_PYTHON"

# 4. 刪除舊的 runtime（避免殘留）
rm -rf tauri_embedded_python

# 5. 用這個專案的 python 來建立「要打包的 runtime」
"$POETRY_PYTHON" -m venv tauri_embedded_python

# 6. 幫 runtime 裝 pip / wheel / setuptools
./tauri_embedded_python/bin/python -m ensurepip --upgrade
./tauri_embedded_python/bin/pip install --upgrade pip setuptools wheel

# 7. 從這個專案目前的 Poetry 環境凍結出實際套件版本清單
poetry run pip freeze > frozen_requirements.txt

# 8. 把這份清單安裝進剛建立的 runtime
./tauri_embedded_python/bin/pip install -r frozen_requirements.txt

# 9. 把你的專案本身裝進 runtime (讓 runtime 可 import 你的程式碼)
./tauri_embedded_python/bin/pip install .
