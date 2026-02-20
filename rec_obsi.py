import whisper
import sounddevice as sd
import scipy.io.wavfile as wav
import customtkinter as ctk
import os
import subprocess
from datetime import datetime
import urllib.parse


import asyncio
import websockets
import threading
import json

from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 환경 변수에서 경로 읽기 (설정이 없으면 기본값 사용)
OBSIDIAN_VAULT_PATH = os.getenv("OBSIDIAN_VAULT_PATH", "./default_vault")

print(f"✅ 로드된 옵시디언 경로: {OBSIDIAN_VAULT_PATH}")

# --- 설정 구간 ---
#MODEL_TYPE = "large-v3"
MODEL_TYPE = "turbo"
DICT_FILE = "personal_dict.txt"
TEMP_AUDIO = "temp_record.wav"

# 모델 로드 (최초 실행 시 다운로드됨)
print("Whisper 모델 로드 중...")
model = whisper.load_model(MODEL_TYPE)
print("Whisper ${model} loaded")

# 장치 목록을 출력해서 ID 확인 (테스트용)
#print(sd.query_devices())

# card 2를 기본 입력 장치로 지정 (보통 'USB PnP Sound Device'가 2번일 확률이 높음)
sd.default.device = 1


class WhisperServer(threading.Thread):
    def __init__(self, app_instance, port=9999):
        super().__init__()
        self.port = port
        self.app = app_instance
        self.connected_clients = set()
        self.loop = None
        self.daemon = True

    def run(self):
        # 1. 이 스레드를 위한 새로운 루프 생성
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        # 2. 루프 안에서 서버를 생성하고 실행
        async def main():
            # websockets.serve를 비동기 컨텍스트에서 실행
            async with websockets.serve(self.handler, "127.0.0.1", self.port):
                await asyncio.Future()  # 서버가 종료되지 않도록 무한 대기

        self.loop.run_until_complete(main())

    async def handler(self, websocket):
        self.connected_clients.add(websocket)
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("type") == "GET_LAST_TEXT":
                    # [핵심] 브라우저가 요청하는 순간 파일을 다시 읽음
                    content = self.read_current_file()
                    if content:
                        await websocket.send(json.dumps({
                            "type": "INSERT_TEXT",
                            "text": content
                        }))
        finally:
            self.connected_clients.remove(websocket)

    def read_current_file(self):
        path = self.app.last_filepath # WhisperApp에서 저장해둔 최신 경로
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()

                # [중요] 읽어간 뒤에 경로를 초기화해서 중복 전송 방지
                self.app.last_filepath = ""
                return content

            except Exception as e:
                print(f"파일 읽기 실패: {e}")
        return None

    def send_message(self, text):
        if not self.connected_clients:
            print("연결된 브라우저가 없습니다.")
            return

        if self.loop is None:
            return

        message = json.dumps({"type": "INSERT_TEXT", "text": text})

        # 스레드 세이프하게 비동기 작업 예약
        for client in list(self.connected_clients):
            try:
                asyncio.run_coroutine_threadsafe(client.send(message), self.loop)
            except Exception as e:
                print(f"전송 중 오류: {e}")

class WhisperApp(ctk.CTk):
    def __init__(self, ws_server):
        super().__init__()
        self.ws_server = ws_server  # 전달받은 서버 인스턴스 저장
        self.title("Whisper STT")
        self.geometry("400x250")
        
        # 최근 처리된 텍스트를 저장할 변수
        self.last_text = ""
        # 마지막으로 생성된 옵시디언 파일 경로를 저장
        self.last_filepath = ""

        # UI 레이아웃
        self.status_label = ctk.CTkLabel(self, text="준비됨")
        self.status_label.pack(pady=10)

        # 버튼 프레임 (녹음과 전송 버튼을 가로로 배치하기 위함)
        self.button_frame = ctk.CTkFrame(self)
        self.button_frame.pack(pady=20)


        self.is_recording = False
        self.recording_data = []
        #self.fs = 16000 # Whisper 권장 샘플링 레이트
        self.fs = 44100 # Whisper 권장 샘플링 레이트

        self.btn = ctk.CTkButton(self, text="녹음 시작", command=self.toggle_record, width=200, height=60)
        self.btn.pack(expand=True)
        
        self.status_label = ctk.CTkLabel(self, text="준비됨")
        self.status_label.pack(pady=10)


        # [전송] 버튼 추가
        self.send_btn = ctk.CTkButton(
            self.button_frame,
            text="브라우저 전송",
            fg_color="green",
            hover_color="darkgreen",
            command=self.handle_send_click
        )
        self.send_btn.pack(side="left", padx=10)

    def handle_send_click(self):

        if not self.last_filepath:
            return

        # 1. 파이어폭스 창을 찾아서 강제로 포커스 주기
        # (창 제목에 'Firefox'가 포함된 창을 맨 앞으로 가져옵니다)
        subprocess.run(["wmctrl", "-a", "Firefox"])

        # 2. 브라우저가 포커스를 잡을 때까지 아주 잠깐 대기 (0.2초)  
        import time
        time.sleep(0.2)

        """전송 버튼 클릭 시 동작: 저장된 파일을 다시 읽어서 전송"""
        if self.last_filepath and os.path.exists(self.last_filepath):
            try:
                # 옵시디언 파일을 다시 읽음 (수정된 내용 반영)
                with open(self.last_filepath, "r", encoding="utf-8") as f:
                    updated_text = f.read()

                # 웹소켓으로 전송
                self.ws_server.send_message(updated_text)
                self.status_label.configure(text="수정된 내용 전송 완료!")
                print(f"전송된 내용: {updated_text}")
            except Exception as e:
                self.status_label.configure(text=f"파일 읽기 오류: {e}")
        else:
            self.status_label.configure(text="전송할 파일이 없습니다.")

    def toggle_record(self):
        if not self.is_recording:
            self.start_record()
        else:
            self.stop_record()

    def start_record(self):
        self.is_recording = True
        self.recording_data = []
        self.btn.configure(text="녹음 중지 (완료)", fg_color="red")
        self.status_label.configure(text="말씀하세요...")
        
        # 비동기 녹음 시작
        self.stream = sd.InputStream(samplerate=self.fs, channels=1,
                                     device=1, 
                                     callback=self.callback)
        self.stream.start()

    def callback(self, indata, frames, time, status):
        self.recording_data.append(indata.copy())

    def stop_record(self):
        self.is_recording = False
        self.stream.stop()
        self.stream.close()
        self.btn.configure(text="처리 중...", state="disabled")
        
        # 파일 저장
        import numpy as np
        audio_np = np.concatenate(self.recording_data, axis=0)
        wav.write(TEMP_AUDIO, self.fs, audio_np)
        
        self.process_audio()

    def process_audio(self):
        # 사전 읽기
        prompt = ""
        if os.path.exists(DICT_FILE):
            with open(DICT_FILE, "r", encoding="utf-8") as f:
                prompt = f.read().strip()

        # 변환
        self.status_label.configure(text="텍스트 변환 중...")
        result = model.transcribe(TEMP_AUDIO, initial_prompt=prompt, language="ko")
        text = result["text"]

        # 옵시디언 파일 생성
        filename = datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".md"
        # filepath = os.path.join(OBSIDIAN_VAULT_PATH, filename)
        self.last_filepath = os.path.join(OBSIDIAN_VAULT_PATH, filename)
        
        with open(self.last_filepath, "w", encoding="utf-8") as f:
            #f.write(f"# Whisper 기록 ({datetime.now().strftime('%Y-%m-%d %H:%M')})\n\n")
            f.write(text)

        # 옵시디언 열기 (리눅스 xdg-open 활용)
        # obsidian://open?vault=... 형식도 가능하지만 파일 직접 열기가 가장 확실합니다.
        abs_path = os.path.abspath(self.last_filepath)
        encoded_path = urllib.parse.quote(abs_path)
        obsidian_uri = f"obsidian://open?path={encoded_path}"
        subprocess.Popen(["xdg-open", obsidian_uri])

        #subprocess.run(["xdg-open", filepath])

        self.btn.configure(text="녹음 시작", state="normal", fg_color=["#3B8ED0", "#1F6AA5"])
        self.status_label.configure(text="완료 및 저장됨 (전송 대기)")

if __name__ == "__main__":
    # 2. 메인 앱 시작 시 서버 인스턴스 주입
    app = WhisperApp(ws_server=None)

    # 1. 서버 스레드 시작
    ws_server = WhisperServer(app_instance=app, port=9999)
    app.ws_server = ws_server

    ws_server.start()
    app.mainloop()
