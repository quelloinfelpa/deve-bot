import requests
import time
import threading

class GameBot:
    
    BASE_URL = "https://sososisi.isonlab.net"
    
    def __init__(self, name: str, visible: bool = True, shots_per_target: int = 10):
        self.name = name
        self.visible = visible
        self.shots_per_target = shots_per_target
        self.code = None
        self.ping_interval = 5
        self._running = False
        
    def authenticate(self):
        response = requests.get(f"{self.BASE_URL}/api/auth", params={"name": self.name})
        data = response.json()
        
        self.code = data["code"]
        self.ping_interval = data.get("pingEverySeconds", 5)
        
        print(f"Codice: {self.code}")
        return self.code
    
    def ping(self):
        visibility = "visible" if self.visible else "invisible"
        response = requests.get(
            f"{self.BASE_URL}/api/ping",
            params={"code": self.code, "visible": visibility}
        )
        result = response.json()
        
        if not result.get("ok"):
            self.authenticate()
            return False
        
        return True
    
    def ping_loop(self):
        while self._running:
            self.ping()
            time.sleep(self.ping_interval)
    
    def get_enemies(self):
        response = requests.get(f"{self.BASE_URL}/api/players", params={"code": self.code})
        players = response.json().get("players", [])
        
        enemies = [
            p["name"] 
            for p in players 
            if p["name"] != self.name and p.get("visible")
        ]
        
        return enemies
    
    def fire_at(self, target: str):
        requests.get(
            f"{self.BASE_URL}/api/fire",
            params={"code": self.code, "target": target}
        )
    
    def fire_volley(self, target: str):
        for _ in range(self.shots_per_target):
            self.fire_at(target)
        print(f"💀 Distrutto {target}")
    
    def fire_loop(self):
        while self._running:
            enemies = self.get_enemies()
            for enemy in enemies:
                if not self._running:
                    break
                self.fire_volley(enemy)
            time.sleep(1)
    
    def start(self):
        self.authenticate()
        self._running = True
        
        ping_thread = threading.Thread(target=self.ping_loop, daemon=True)
        ping_thread.start()
        
        try:
            self.fire_loop()
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        self._running = False


if __name__ == "__main__":
    bot = GameBot(name="sergio_2", visible=True, shots_per_target=10)
    bot.start()