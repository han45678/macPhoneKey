import rumps
import threading
import asyncio
from bleak import BleakScanner
import os
import json
import socket
import http.server
import socketserver
import qrcode
import time
import tempfile
import secrets
import sys
import subprocess

# 設定檔路徑
CONFIG_FILE = os.path.expanduser("~/.macPhoneKey_config.json")

class MacUnlockerApp(rumps.App):
    def __init__(self):
        # 設定 icon 路徑 (相容開發環境與打包後的 App)
        icon_path = self.get_resource_path('icon.png')
        # 設定在選單列顯示 icon，title 設為 None 隱藏文字
        super(MacUnlockerApp, self).__init__("macPhoneKey", title=None, icon=icon_path, quit_button="退出")
        self.menu = ["狀態: WiFi 待命", "顯示配對 QR Code", "重設密碼", "顯示目前密碼", "手動解鎖測試"]
        
        self.auth_token = None
        self.password = None
        self.server_port = 7717
        
        # 嘗試載入設定
        self.load_config()
        
        # 移除這裡的啟動程式碼，移到 check_setup 中執行，避免 UI 未準備好就更新導致閃退

    def get_resource_path(self, filename):
        # 1. 檢查 py2app 環境變數 (最準確)
        if 'RESOURCEPATH' in os.environ:
            return os.path.join(os.environ['RESOURCEPATH'], filename)
        
        # 2. 檢查 frozen 狀態 (py2app/PyInstaller)
        if getattr(sys, 'frozen', False):
            return os.path.join(os.path.dirname(sys.executable), '..', 'Resources', filename)
            
        # 3. 開發環境
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    self.auth_token = data.get("auth_token")
                    self.password = data.get("password")
            except Exception as e:
                print(f"讀取設定失敗: {e}")
        
        # 如果沒有 token，產生一個新的
        if not self.auth_token:
            self.auth_token = secrets.token_hex(16)
            self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({"auth_token": self.auth_token, "password": self.password}, f)

    # 使用計時器，確保 App 啟動完成後才檢查密碼 (只執行一次)
    @rumps.timer(1)
    def check_setup(self, sender):
        sender.stop() # 停止計時器，避免重複執行
        
        # 延遲啟動 Web Server，確保 App UI 已經完全準備好
        threading.Thread(target=self.start_server, daemon=True).start()
        
        if not self.password:
            self.prompt_password()

    def prompt_password(self):
        # 強制將 App 視窗帶到最上層，避免被擋住
        os.system("osascript -e 'tell application \"System Events\" to set frontmost of process \"macPhoneKey\" to true'")
        
        # 使用 rumps 內建視窗 (穩定且原生)，避免 tkinter 衝突
        window = rumps.Window(
            message='請輸入您的 Mac 登入密碼',
            title='設定密碼',
            default_text=self.password if self.password else '',
            ok='儲存',
            cancel='取消',
            dimensions=(300, 20),
            secure=True
        )
        response = window.run()
        if response.clicked:
            self.password = response.text
            self.save_config()

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
        except:
            ip = '127.0.0.1'
        finally:
            s.close()
        return ip

    def start_server(self):
        handler = MacRequestHandler
        handler.app_ref = self
        
        # 嘗試尋找可用 Port (最多嘗試 10 次)
        initial_port = self.server_port
        for port in range(initial_port, initial_port + 10):
            try:
                # 允許重複使用 Port，避免重啟時報錯
                socketserver.TCPServer.allow_reuse_address = True
                httpd = socketserver.TCPServer(("", port), handler)
                
                # 成功綁定後，更新目前的 Port
                self.server_port = port
                print(f"Web Server 啟動於 port {self.server_port}")
                
                # 更新選單顯示目前 IP，讓使用者知道連線資訊
                ip = self.get_local_ip()
                self.menu["狀態: WiFi 待命"].title = f"監聽中: {ip}:{self.server_port}"
                
                with httpd:
                    httpd.serve_forever()
                return
            except OSError as e:
                if e.errno == 48: # Address already in use
                    print(f"Port {port} 被佔用，嘗試下一個...")
                    continue
                elif e.errno == 13: # Permission denied
                    rumps.notification("權限錯誤", f"無法使用 Port {port}", "請使用 sudo 執行或改用 Port 1024 以上")
                    return
                else:
                    rumps.notification("錯誤", "無法啟動 Web Server", f"Port {port} 發生錯誤: {e}")
                    return
        
        rumps.notification("錯誤", "無法啟動 Web Server", f"Port {initial_port} 到 {initial_port + 9} 皆被佔用")

    @rumps.clicked("顯示配對 QR Code")
    def show_qr_code(self, _):
        # 取得本機 IP
        ip = self.get_local_ip()
        
        if ip == '127.0.0.1':
            rumps.notification("警告", "無法偵測 IP", "請確認 Mac 已連上 WiFi")

        # 產生帶有 Token 的網址
        url = f"http://{ip}:{self.server_port}/?token={self.auth_token}"
        print(f"配對網址: {url}")

        # 產生 QR Code
        qr = qrcode.make(url)
        qr_path = os.path.join(tempfile.gettempdir(), "mac_key_qr.png")
        qr.save(qr_path)
        os.system(f"open {qr_path}") # 使用預覽程式開啟圖片

    @rumps.clicked("重設密碼")
    def reset_password_menu(self, _):
        self.prompt_password()

    @rumps.clicked("顯示目前密碼")
    def show_current_password(self, _):
        if self.password:
            rumps.alert("目前儲存的密碼", self.password)
        else:
            rumps.alert("尚未設定密碼")

    @rumps.clicked("手動解鎖測試")
    def test_unlock(self, _):
        self.unlock_mac()
        rumps.notification("Mac 解鎖器", "測試成功", "已執行解鎖指令")

    def unlock_mac(self):
        if not self.password:
            rumps.notification("錯誤", "密碼未設定", "請點選選單中的「重設密碼」")
            return

        print("執行解鎖程序...")
        # 1. 喚醒螢幕 (如果螢幕關閉，這步很重要)
        # 改用 subprocess 在背景執行，不阻塞程式，並延長至 5 秒確保輸入期間螢幕亮著
        subprocess.Popen(["caffeinate", "-u", "-t", "5"])

        # 2. 輸入密碼
        # 安全性修正: 轉義密碼中的特殊字元，並使用 subprocess 避免 Shell Injection
        safe_password = self.password.replace("\\", "\\\\").replace('"', '\\"')
        
        script = f'''tell application "System Events"
            delay 1.0
            keystroke "{safe_password}"
            delay 0.2
            keystroke return
        end tell'''

        try:
            # 使用 subprocess.run 直接執行，不透過 shell
            subprocess.run(["osascript", "-e", script], check=True)
        except subprocess.CalledProcessError as e:
            print(f"解鎖指令執行失敗: {e}")

# 處理 HTTP 請求
class MacRequestHandler(http.server.SimpleHTTPRequestHandler):
    app_ref = None 

    def do_GET(self):
        # 如果是根目錄，回傳 phoneKey.html
        if self.path == "/" or self.path.startswith("/?token="):
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            
            # 讀取 HTML 檔案內容
            html_content = "<h1>Error: phoneKey.html not found</h1>"
            html_path = self.app_ref.get_resource_path('phoneKey.html')
            
            if os.path.exists(html_path):
                with open(html_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
            
            self.wfile.write(html_content.encode('utf-8'))
            return
        
        # 安全性修正: 阻擋所有其他路徑，防止目錄遍歷
        self.send_error(404, "File not found")

    def do_POST(self):
        if self.path == "/unlock":
            # 讀取 POST data 中的 token
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            
            # 安全性修正: 使用 JSON 解析並嚴格比對 Token
            try:
                data = json.loads(post_data)
                if data.get("token") == self.app_ref.auth_token:
                    self.app_ref.unlock_mac()
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Unlocked")
                else:
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Forbidden")
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid JSON")

if __name__ == "__main__":
    MacUnlockerApp().run()