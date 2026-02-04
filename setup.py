"""
這是用於將 mac_listener.py 打包成 macOS 應用程式 (.app) 的設定檔。
使用方式:
1. 確保已安裝 py2app: pip install py2app
2. 執行打包指令: python setup.py py2app
"""

from setuptools import setup

APP = ['mac_listener.py']
DATA_FILES = ['phoneKey.html', 'icon.png']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon.png',
    'plist': {
        'LSUIElement': True,  # 讓 App 只顯示在選單列 (Menu Bar)，不顯示在 Dock
        'NSCameraUsageDescription': 'macFaceKey 需要使用相機來進行人臉辨識解鎖',
    },
    # 只保留 face_recognition_models 以確保模型資料夾被完整複製
    # 其他如 cv2, dlib, numpy 等由 site_packages=True 自動處理，這樣最穩定
    'packages': ['face_recognition_models'],
    # 移除 dlib, cv2, numpy 等複雜套件的 includes，避免 py2app 找不到路徑報錯
    # 讓 site_packages=True 自動將環境中的套件整包複製進去
    'includes': ['rumps', 'os', 'sys', 'json', 'threading', 'socket', 'http.server', 'subprocess', 'secrets', 'base64', 'time', 'traceback'],
    'site_packages': True,
}

setup(
    app=APP,
    name='macFaceKey',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
)