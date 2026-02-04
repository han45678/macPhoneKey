#!/bin/bash
set -e # 遇到任何錯誤立即停止執行

# 定義錯誤捕捉，讓你知道哪一行出錯
trap 'echo "❌ 錯誤發生在第 $LINENO 行"; exit 1' ERR

echo "🔧 正在檢查環境..."

# 1. 檢查是否安裝了 CMake (dlib 需要)
if ! command -v cmake &> /dev/null; then
    echo "⚠️  未偵測到 CMake，正在嘗試透過 Homebrew 安裝..."
    if command -v brew &> /dev/null; then
        # 安裝 dlib 編譯所需的所有依賴: cmake, jpeg, libpng, openblas
        echo "🍺 正在安裝編譯依賴 (cmake, jpeg, libpng, openblas)..."
        brew install cmake jpeg libpng openblas
    else
        echo "❌ 請先安裝 Homebrew (https://brew.sh/) 或手動安裝 CMake，否則 dlib 無法安裝。"
        exit 1
    fi
else
    # 即使有 cmake，也嘗試安裝依賴庫以防萬一 (如果有 brew)
    if command -v brew &> /dev/null; then
        brew install jpeg libpng openblas || true
    fi
fi

# 設定編譯參數，協助 dlib 找到 Homebrew 安裝的 jpeg/libpng
if command -v brew &> /dev/null; then
    BREW_PREFIX=$(brew --prefix)
    # 使用 += 避免覆蓋現有設定，並加入 openblas 路徑
    export CFLAGS="-I$BREW_PREFIX/include -I$BREW_PREFIX/opt/openblas/include $CFLAGS"
    export LDFLAGS="-L$BREW_PREFIX/lib -L$BREW_PREFIX/opt/openblas/lib $LDFLAGS"
    echo "🍺 Homebrew 路徑: $BREW_PREFIX (已設定 CFLAGS/LDFLAGS)"
fi

echo " 正在建立獨立虛擬環境 (解決檔案衝突問題)..."
# 移除舊的虛擬環境與打包檔，確保環境絕對乾淨
rm -rf venv build dist *.egg-info

# 建立並啟動虛擬環境
python3 -m venv venv
source venv/bin/activate

echo "📦 正在虛擬環境中安裝依賴..."
pip install --upgrade pip setuptools wheel

# 設定環境變數以解決 dlib 在 macOS 上的編譯問題 (停用 X11/GUI 依賴)
export DLIB_NO_GUI_SUPPORT=1 
export CMAKE_ARGS="-DDLIB_NO_GUI_SUPPORT=ON"

# 分開安裝 dlib 以便除錯，並確保參數生效
echo "📦 正在編譯 dlib (這可能需要幾分鐘，請勿關閉)..."
pip install dlib --no-cache-dir

pip install py2app rumps opencv-python face_recognition face_recognition_models numpy pyobjc-framework-Quartz Pillow

echo "🚀 開始打包 (這可能需要幾分鐘，請耐心等待)..."
# 使用虛擬環境中的 python 執行打包
python3 setup.py py2app

if [ -d "dist/macFaceKey.app" ]; then
    echo "✅ 打包成功！應用程式位於 dist/macFaceKey.app"
    open dist
else
    echo "❌ 打包失敗，請檢查上方的錯誤訊息。"
fi