import websocket
import json
import threading
import time
import socket
import struct
from colorama import init, Fore
import sys

init(autoreset=True)

class DiscordVoiceBot:
    def __init__(self, token: str):
        self.token = token
        self.ws = None
        self.voice_ws = None
        self.running = True
        self.heartbeat_interval = None
        self.heartbeat_thread = None
        self.voice_heartbeat_thread = None
        self.sequence = None
        self.user_id = None
        self.session_id = None
        self.identified = False
        self.voice_connected = False
        
        # Voice gateway info
        self.voice_endpoint = None
        self.voice_token = None
        self.server_id = None
        self.voice_heartbeat_interval = None
        self.voice_ssrc = None
        self.voice_port = None
        self.voice_ip = None
        self.secret_key = None
        
        # UDP socket
        self.udp_socket = None
        self.udp_thread = None
        
        # Parameters
        self.guild_id = None
        self.channel_id = None
        
        # Voice state
        self.self_mute = False
        self.self_deaf = False
        self.self_video = False
        self.self_stream = False
        
        # Voice retry
        self.voice_retry_count = 0
        self.max_voice_retries = 3
        
    def on_message(self, ws, message):
        """Xử lý message từ Discord Gateway"""
        try:
            data = json.loads(message)
            op = data.get('op')
            t = data.get('t')
            s = data.get('s')
            
            if s:
                self.sequence = s
            
            if op == 10:  # Hello
                self.heartbeat_interval = data['d']['heartbeat_interval'] / 1000
                print(f"{Fore.GREEN}[✅] Gateway Connected - Heartbeat: {self.heartbeat_interval}s")
                
                self.heartbeat_thread = threading.Thread(target=self.send_heartbeat, daemon=True)
                self.heartbeat_thread.start()
                
                self.identify()
                
            elif t == "READY":
                self.user_id = data['d']['user']['id']
                self.session_id = data['d']['session_id']
                self.identified = True
                print(f"{Fore.GREEN}[✅] READY - User: {self.user_id}")
                
                time.sleep(0.2)
                self.voice_state_update(self.guild_id, self.channel_id)
                
            elif t == "VOICE_STATE_UPDATE":
                d = data.get('d', {})
                if d.get('guild_id') == self.guild_id and d.get('channel_id') == self.channel_id:
                    print(f"{Fore.CYAN}[🎤] Voice State Updated")
                
            elif t == "VOICE_SERVER_UPDATE":
                self.voice_endpoint = data['d'].get('endpoint')
                self.voice_token = data['d'].get('token')
                self.server_id = data['d'].get('guild_id')
                
                if self.voice_endpoint:
                    print(f"{Fore.CYAN}[🔗] Received Voice Endpoint")
                    time.sleep(0.5)
                    self.voice_retry_count = 0
                    self.connect_voice_gateway()
                
            elif op == 9:
                print(f"{Fore.RED}[❌] Invalid Session - Token banned!")
                self.running = False
                
        except Exception as e:
            print(f"{Fore.RED}[❌] Gateway Error: {e}")

    def on_error(self, ws, error):
        """Xử lý error"""
        print(f"{Fore.RED}[❌] WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        """Khi kết nối đóng"""
        print(f"{Fore.YELLOW}[⚠️] Gateway Disconnected - Code: {close_status_code}")
        self.running = False

    def on_open(self, ws):
        """Khi kết nối mở"""
        print(f"{Fore.GREEN}[✅] WebSocket Connected")

    def send_heartbeat(self):
        """Gửi heartbeat tới Gateway"""
        while self.running and self.heartbeat_interval:
            try:
                time.sleep(self.heartbeat_interval - 1)
                if self.ws and self.ws.sock:
                    self.ws.send(json.dumps({"op": 1, "d": self.sequence}))
            except Exception as e:
                print(f"{Fore.RED}[❌] Heartbeat error: {e}")
                break

    def send_voice_heartbeat(self):
        """Gửi heartbeat tới Voice Gateway"""
        while self.running and self.voice_heartbeat_interval and self.voice_ws and self.voice_connected:
            try:
                time.sleep(self.voice_heartbeat_interval / 1000 - 0.1)
                if self.voice_ws and self.voice_ws.sock:
                    self.voice_ws.send(json.dumps({
                        "op": 3,
                        "d": int(time.time() * 1000)
                    }))
            except Exception as e:
                print(f"{Fore.RED}[❌] Voice Heartbeat error: {e}")
                self.voice_connected = False
                break

    def send_udp_heartbeat(self):
        """Gửi UDP keepalive packets"""
        try:
            while self.running and self.udp_socket and self.voice_connected:
                time.sleep(5)
                if self.udp_socket:
                    packet = struct.pack('>I', 0)
                    self.udp_socket.sendto(packet, (self.voice_ip, self.voice_port))
        except Exception as e:
            print(f"{Fore.RED}[❌] UDP Keepalive error: {e}")
            self.voice_connected = False

    def identify(self):
        """Gửi IDENTIFY payload - Discord API v10"""
        identify_payload = {
            "op": 2,
            "d": {
                "token": self.token,
                "intents": 513,
                "properties": {
                    "os": "Linux",
                    "browser": "Discord Client",
                    "device": "Discord Client",
                    "system_locale": "en-US",
                    "browser_user_agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                    "browser_version": "",
                    "os_version": "",
                    "referrer": "",
                    "referring_domain": ""
                },
                "compress": False,
                "large_threshold": 250
            }
        }
        self.ws.send(json.dumps(identify_payload))
        print(f"{Fore.CYAN}[📤] Sending IDENTIFY...")

    def voice_state_update(self, guild_id: str, channel_id: str):
        """Gửi VOICE_STATE_UPDATE"""
        if not self.identified:
            return
            
        voice_state_payload = {
            "op": 4,
            "d": {
                "guild_id": guild_id,
                "channel_id": channel_id,
                "self_mute": self.self_mute,
                "self_deaf": self.self_deaf,
                "self_video": self.self_video,
                "self_stream": self.self_stream
            }
        }
        self.ws.send(json.dumps(voice_state_payload))
        print(f"{Fore.CYAN}[📤] Joining Voice Channel...")

    def fake_stream_create(self):
        """Tạo fake live stream - op=18"""
        if not self.identified:
            return
            
        fake_stream_payload = {
            "op": 18,
            "d": {
                "type": "guild",
                "guild_id": self.guild_id,
                "channel_id": self.channel_id,
                "preferred_region": None
            }
        }
        self.ws.send(json.dumps(fake_stream_payload))
        print(f"{Fore.MAGENTA}[🎥] Fake Live Stream Started")

    def toggle_mute(self, mute: bool):
        """Bật/tắt mic"""
        self.self_mute = mute
        self.voice_state_update(self.guild_id, self.channel_id)
        status = "Muted" if mute else "Unmuted"
        print(f"{Fore.YELLOW}[🎤] Mic {status}")

    def toggle_deaf(self, deaf: bool):
        """Bật/tắt loa"""
        self.self_deaf = deaf
        self.voice_state_update(self.guild_id, self.channel_id)
        status = "Deafened" if deaf else "Undeafened"
        print(f"{Fore.YELLOW}[🔊] Speaker {status}")

    def voice_identify(self):
        """Gửi IDENTIFY tới Voice Gateway - Voice v9"""
        identify_payload = {
            "op": 0,
            "d": {
                "server_id": self.server_id,
                "user_id": self.user_id,
                "session_id": self.session_id,
                "token": self.voice_token
            }
        }
        self.voice_ws.send(json.dumps(identify_payload))
        print(f"{Fore.CYAN}[📤] Voice IDENTIFY sent...")

    def voice_on_message(self, ws, message):
        """Xử lý message từ Voice Gateway"""
        try:
            data = json.loads(message)
            op = data.get('op')
            
            if op == 8:  # Hello
                self.voice_heartbeat_interval = data['d']['heartbeat_interval']
                print(f"{Fore.GREEN}[✅] Voice Gateway Ready")
                
                self.voice_identify()
                
                self.voice_heartbeat_thread = threading.Thread(target=self.send_voice_heartbeat, daemon=True)
                self.voice_heartbeat_thread.start()
                
            elif op == 2:  # Ready
                self.voice_ssrc = data['d'].get('ssrc')
                self.voice_ip = data['d'].get('ip')
                self.voice_port = data['d'].get('port')
                
                print(f"{Fore.GREEN}[✅] Voice Ready - SSRC: {self.voice_ssrc}")
                
                self.setup_udp_socket()
                
                self.udp_thread = threading.Thread(target=self.send_udp_heartbeat, daemon=True)
                self.udp_thread.start()
                
                self.voice_connected = True
                
                # Fake stream sau khi voice ready
                time.sleep(0.2)
                self.fake_stream_create()
                    
            elif op == 4:  # Session Description
                mode = data['d'].get('mode')
                secret_key = data['d'].get('secret_key')
                
                if secret_key:
                    self.secret_key = secret_key
                    print(f"{Fore.GREEN}[✅] Session Description Received - Mode: {mode}")
                    print(f"{Fore.MAGENTA}[🎉] ✨ TREO VOICE THÀNH CÔNG ✨")
                    self.voice_connected = True
                
            elif op == 5:  # Speaking
                pass
                
        except json.JSONDecodeError:
            pass
        except Exception as e:
            print(f"{Fore.RED}[❌] Voice message error: {e}")

    def setup_udp_socket(self):
        """Tạo UDP socket cho voice"""
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(("0.0.0.0", 0))
        except Exception as e:
            print(f"{Fore.RED}[❌] UDP socket error: {e}")

    def voice_on_error(self, ws, error):
        """Xử lý error voice"""
        if "Session is no longer valid" in str(error):
            print(f"{Fore.YELLOW}[⚠️] Session expired - Reconnecting...")
            self.voice_connected = False
            if self.voice_retry_count < self.max_voice_retries:
                self.voice_retry_count += 1
                time.sleep(2)
                self.connect_voice_gateway()
        else:
            print(f"{Fore.RED}[❌] Voice error: {error}")
            self.voice_connected = False

    def voice_on_close(self, ws, close_status_code, close_msg):
        """Khi voice kết nối đóng"""
        self.voice_connected = False
        if close_status_code != 1000 and self.running:
            print(f"{Fore.YELLOW}[⚠️] Voice disconnected - Reconnecting...")
            if self.voice_retry_count < self.max_voice_retries:
                self.voice_retry_count += 1
                time.sleep(2)
                self.connect_voice_gateway()

    def voice_on_open(self, ws):
        """Khi voice kết nối mở"""
        print(f"{Fore.GREEN}[✅] Voice WebSocket Connected")

    def connect_voice_gateway(self):
        """Kết nối tới Voice Gateway - Voice v9"""
        if not self.voice_endpoint or not self.voice_token:
            print(f"{Fore.RED}[❌] Missing endpoint or token")
            return
        
        try:
            endpoint = self.voice_endpoint
            if ':' in endpoint:
                endpoint = endpoint.split(':')[0]
            
            ws_url = f"wss://{endpoint}/?v=9&encoding=json"
            
            self.voice_ws = websocket.WebSocketApp(
                ws_url,
                on_open=self.voice_on_open,
                on_message=self.voice_on_message,
                on_error=self.voice_on_error,
                on_close=self.voice_on_close
            )
            
            voice_thread = threading.Thread(target=self.voice_ws.run_forever, daemon=True)
            voice_thread.start()
            
        except Exception as e:
            print(f"{Fore.RED}[❌] Voice connection error: {e}")

    def connect(self, guild_id: str, channel_id: str):
        """Kết nối tới Discord Gateway - API v10"""
        self.guild_id = guild_id
        self.channel_id = channel_id
        
        try:
            ws_url = "wss://gateway.discord.gg/?v=10&encoding=json"
            print(f"{Fore.CYAN}[🔗] Connecting to Discord Gateway...\n")
            
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_open=self.on_open,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close
            )
            
            self.ws.run_forever()
            
        except Exception as e:
            print(f"{Fore.RED}[❌] Connection error: {e}")
        finally:
            self.running = False
            if self.ws:
                try:
                    self.ws.close()
                except:
                    pass
            if self.voice_ws:
                try:
                    self.voice_ws.close()
                except:
                    pass
            if self.udp_socket:
                try:
                    self.udp_socket.close()
                except:
                    pass

def main():
    print(f"{Fore.CYAN}╔════════════════════════════════════════════╗")
    print(f"{Fore.CYAN}║    Discord Voice Bot v2 (Full Features)    ║")
    print(f"{Fore.CYAN}║  Gateway v10 + Voice v9 + Fake Stream      ║")
    print(f"{Fore.CYAN}╚════════════════════════════════════════════╝\n")
    
    token = input(f"{Fore.CYAN}Discord Token: ").strip()
    if not token:
        print(f"{Fore.RED}❌ Token cannot be empty")
        return

    guild_id = input(f"{Fore.CYAN}Guild ID: ").strip()
    channel_id = input(f"{Fore.CYAN}Channel ID: ").strip()
    
    if not guild_id or not channel_id:
        print(f"{Fore.RED}❌ Guild ID or Channel ID cannot be empty")
        return

    print(f"\n{Fore.GREEN}Connecting...\n")

    bot = DiscordVoiceBot(token)

    # Thread để xử lý bot
    bot_thread = threading.Thread(target=bot.connect, args=(guild_id, channel_id), daemon=True)
    bot_thread.start()

    # Menu điều khiển
    print(f"\n{Fore.YELLOW}╔════════════════════════════════════════════╗")
    print(f"{Fore.YELLOW}║         VOICE CONTROL MENU                 ║")
    print(f"{Fore.YELLOW}║  [1] Mute Mic      [2] Unmute Mic         ║")
    print(f"{Fore.YELLOW}║  [3] Deafen        [4] Undeafen           ║")
    print(f"{Fore.YELLOW}║  [5] Fake Stream   [0] Exit               ║")
    print(f"{Fore.YELLOW}╚════════════════════════════════════════════╝\n")

    try:
        while bot.running:
            try:
                cmd = input(f"{Fore.CYAN}Command > ").strip()
                
                if cmd == "1":
                    bot.toggle_mute(True)
                elif cmd == "2":
                    bot.toggle_mute(False)
                elif cmd == "3":
                    bot.toggle_deaf(True)
                elif cmd == "4":
                    bot.toggle_deaf(False)
                elif cmd == "5":
                    bot.fake_stream_create()
                elif cmd == "0":
                    print(f"{Fore.YELLOW}[⚠️] Exiting...")
                    bot.running = False
                    break
                else:
                    print(f"{Fore.RED}❌ Invalid command")
            except EOFError:
                break
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}⚠️ Program closed.")
        bot.running = False

if __name__ == "__main__":
    main()
