import os
import sys
import traceback

# 設定錯誤日誌路徑 (桌面)
ERROR_LOG = os.path.expanduser("~/Desktop/macFaceKey_error.log")
DEBUG_LOG = os.path.expanduser("~/Desktop/macFaceKey_debug.log")

def log_debug(msg):
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")
    except:
        pass

try:
    import rumps
    import threading
    import json
    import socket
    import http.server
    import socketserver
    import time
    import secrets
    import subprocess
    import cv2
    import face_recognition
    import numpy as np
    import base64
    import Quartz # 需要 pip install pyobjc-framework-Quartz
except Exception as e:
    # 如果引用套件失敗，寫入錯誤日誌並退出
    with open(ERROR_LOG, "w") as f:
        f.write(f"啟動錯誤 (Import Error):\n{traceback.format_exc()}")
    # 嘗試跳出系統警告視窗，讓使用者知道發生錯誤
    os.system(f"osascript -e 'display alert \"App 啟動失敗\" message \"請查看桌面上的 macFaceKey_error.log 以了解詳細原因。\"'")
    sys.exit(1)

# 設定檔路徑
CONFIG_FILE = os.path.expanduser("~/.macFaceKey_config.json")

class MacUnlockerApp(rumps.App):
    def __init__(self):
        # 設定 icon 路徑 (相容開發環境與打包後的 App)
        icon_path = self.get_resource_path('icon.png')
        # 設定在選單列顯示 icon，title 設為 None 隱藏文字
        super(MacUnlockerApp, self).__init__("macFaceKey", title=None, icon=icon_path, quit_button="退出")
        self.menu = ["狀態: 監控中", "開啟註冊頁面", "重設密碼", "顯示目前密碼", "手動解鎖測試"]
        
        self.auth_token = None
        self.password = None
        self.server_port = 7717
        self.known_face_encodings = []
        self.is_camera_running = False
        
        # 嘗試載入設定
        self.load_config()
        
        # 啟動鎖定監控執行緒
        threading.Thread(target=self.monitor_lock_state, daemon=True).start()
        log_debug("應用程式啟動，等待鎖定...")

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
                    
                    # 載入人臉特徵
                    saved_encodings = data.get("face_encodings", [])
                    self.known_face_encodings = [np.array(e) for e in saved_encodings]
                    print(f"已載入 {len(self.known_face_encodings)} 組人臉資料")

            except Exception as e:
                print(f"讀取設定失敗: {e}")
        
        # 如果沒有 token，產生一個新的
        if not self.auth_token:
            self.auth_token = secrets.token_hex(16)
            self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump({
                "auth_token": self.auth_token, 
                "password": self.password,
                "face_encodings": [e.tolist() for e in self.known_face_encodings]
            }, f)

    # 使用計時器，確保 App 啟動完成後才檢查密碼 (只執行一次)
    @rumps.timer(1)
    def check_setup(self, sender):
        sender.stop() # 停止計時器，避免重複執行
        
        # 延遲啟動 Web Server，確保 App UI 已經完全準備好
        threading.Thread(target=self.start_server, daemon=True).start()
        
        # 移除自動跳出密碼輸入，改由使用者手動設定，符合「先配對、再設密碼」的流程
        if not self.password:
            rumps.notification("歡迎使用", "請先註冊人臉", "請點選選單「開啟註冊頁面」並設定 Mac 密碼")

    def prompt_password(self):
        # 強制將 App 視窗帶到最上層，避免被擋住
        os.system("osascript -e 'tell application \"System Events\" to set frontmost of process \"macFaceKey\" to true'")
        
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
                self.menu["狀態: 監控中"].title = f"Web: {ip}:{self.server_port}"
                
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

    @rumps.clicked("開啟註冊頁面")
    def open_register_page(self, _):
        url = f"http://localhost:{self.server_port}/?token={self.auth_token}"
        os.system(f"open '{url}'")

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

    # --- 核心功能：鎖定監控與人臉辨識 ---
    def is_screen_locked(self):
        # 使用 Quartz 檢查螢幕鎖定狀態
        try:
            d = Quartz.CGSessionCopyCurrentDictionary()
            return d and d.get("CGSSessionScreenIsLocked", 0) == 1
        except:
            return False

    def monitor_lock_state(self):
        log_debug("啟動鎖定狀態監控執行緒...")
        try:
            while True:
                if self.is_screen_locked():
                    if not self.is_camera_running:
                        log_debug("偵測到螢幕鎖定，準備啟動相機...")
                        self.start_camera_unlock_loop()
                else:
                    if self.is_camera_running:
                        log_debug("螢幕已解鎖，停止監控")
                    self.is_camera_running = False
                time.sleep(1)
        except Exception as e:
            err_msg = f"監控執行緒崩潰:\n{traceback.format_exc()}"
            log_debug(err_msg)
            with open(ERROR_LOG, "a") as f: f.write(err_msg)

    def start_camera_unlock_loop(self):
        self.is_camera_running = True
        log_debug("正在開啟相機...")
        
        # 開啟鏡頭
        video_capture = cv2.VideoCapture(0)
        if not video_capture.isOpened():
            log_debug("❌ 無法開啟鏡頭 (可能被系統阻擋或無權限)")
            self.is_camera_running = False
            time.sleep(2) # 避免失敗後瘋狂重試
            return

        last_frame = None
        frame_count = 0

        try:
            while self.is_screen_locked() and self.is_camera_running:
                ret, frame = video_capture.read()
                if not ret:
                    log_debug("❌ 無法讀取影像 (畫面全黑或相機斷線)")
                    break

                # 1. 移動偵測 (節省資源，有動靜才辨識)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                if last_frame is None:
                    last_frame = gray
                    continue

                frame_delta = cv2.absdiff(last_frame, gray)
                thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
                motion_score = np.sum(thresh)
                last_frame = gray

                # 如果變動像素超過一定閾值 (代表有人在動)
                # 降低門檻 5000 -> 3000，讓它更容易觸發
                if motion_score > 3000: 
                    log_debug(f"偵測到移動 (分數: {motion_score})，尋找人臉...")
                    
                    # 2. 人臉辨識
                    # 縮小圖片以加快處理速度
                    small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                    rgb_small_frame = small_frame[:, :, ::-1] # BGR to RGB

                    # 偵測人臉位置
                    face_locations = face_recognition.face_locations(rgb_small_frame)
                    
                    if face_locations:
                        log_debug(f"抓到 {len(face_locations)} 張人臉，開始比對...")
                        face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

                        for face_encoding in face_encodings:
                            # 放寬 tolerance: 0.45 -> 0.5 (數字越大越寬鬆)
                            matches = face_recognition.compare_faces(self.known_face_encodings, face_encoding, tolerance=0.5)
                            
                            if True in matches:
                                log_debug("✅ 人臉辨識成功！執行解鎖")
                                self.unlock_mac()
                                # 解鎖後暫停一下，避免重複觸發
                                time.sleep(5)
                                self.is_camera_running = False # 停止迴圈
                                break
                            else:
                                log_debug("⚠️ 辨識失敗 (身分不符)")
                
                # 稍微休息，避免 CPU 100%
                time.sleep(0.1)
        except Exception as e:
            log_debug(f"鏡頭迴圈發生錯誤: {e}")
        finally:
            video_capture.release()
            self.is_camera_running = False
            log_debug("停止鏡頭監控")

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
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(post_data)
            
            # 驗證 Token
            if data.get("token") != self.app_ref.auth_token:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Forbidden")
                return

            if self.path == "/register":
                # 接收註冊照片
                images_b64 = data.get("images", [])
                print(f"收到 {len(images_b64)} 張註冊照片，開始處理...")
                
                new_encodings = []
                for img_str in images_b64:
                    # 解碼 Base64 圖片
                    if "," in img_str:
                        img_str = img_str.split(",")[1]
                    img_data = base64.b64decode(img_str)
                    np_arr = np.frombuffer(img_data, np.uint8)
                    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
                    
                    # 計算特徵值
                    encs = face_recognition.face_encodings(img)
                    if encs:
                        new_encodings.append(encs[0])
                
                if new_encodings:
                    self.app_ref.known_face_encodings.extend(new_encodings)
                    self.app_ref.save_config()
                    print(f"成功註冊 {len(new_encodings)} 組特徵")
                    
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Registered")
                else:
                    print("無法從照片中提取特徵")
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"No faces found")

        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"Invalid JSON")

if __name__ == "__main__":
    try:
        MacUnlockerApp().run()
    except Exception as e:
        # 捕捉啟動錯誤並寫入桌面 Log，方便除錯
        with open(ERROR_LOG, "w") as f:
            f.write(f"執行錯誤 (Runtime Error):\n{traceback.format_exc()}")