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
    'argv_emulation': True,
    'iconfile': 'icon.png',
    'plist': {
        'LSUIElement': True,  # 讓 App 只顯示在選單列 (Menu Bar)，不顯示在 Dock
        'NSBluetoothAlwaysUsageDescription': 'macPhoneKey 需要藍牙權限來偵測您的手機以進行解鎖',
        'NSBluetoothPeripheralUsageDescription': 'macPhoneKey 需要藍牙權限來偵測您的手機以進行解鎖',
    },
    'packages': ['rumps', 'bleak', 'qrcode', 'PIL'],
}

setup(
    app=APP,
    name='macPhoneKey',
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)