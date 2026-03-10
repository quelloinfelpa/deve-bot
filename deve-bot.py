import requests
import time
import threading

BASE_URL = "https://sososisi.isonlab.net"

code = requests.get(f"{BASE_URL}/api/auth?name=TangiBots").json()["code"]
print(f"Codice: {code}")

def ping_loop():
    global code
    while True:
        ping = requests.get(f"{BASE_URL}/api/ping?code={code}&visible=visible").json()
        if not ping.get("ok"):
            code = requests.get(f"{BASE_URL}/api/auth?name=TangiBots").json()["code"]
        time.sleep(5)

def fire_loop():
    while True:
        players = requests.get(f"{BASE_URL}/api/players?code={code}").json().get("players", [])
        nemici = [p["name"] for p in players if p["name"] != "TangiBots" and p.get("visible")]
        for nome in nemici:
            for _ in range(10):
                requests.get(f"{BASE_URL}/api/fire?code={code}&target={nome}")
            print(f"💀 Distrutto {nome}")
        time.sleep(1)

threading.Thread(target=ping_loop, daemon=True).start()
fire_loop()