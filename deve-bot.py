import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict

class GameBotTurbo:
    
    BASE_URL = "https://sososisi.isonlab.net"
    
    def __init__(
        self, 
        name: str, 
        visible: bool = True, 
        shots_per_target: int = 20,
        max_workers: int = 5,  # Thread paralleli per sparare
        fire_delay: float = 0.01  # Delay minimo tra colpi (10ms)
    ):
        self.name = name
        self.visible = visible
        self.shots_per_target = shots_per_target
        self.max_workers = max_workers
        self.fire_delay = fire_delay
        self.code = None
        self.ping_interval = 5
        self._running = False
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        
    def authenticate(self):
        response = requests.get(f"{self.BASE_URL}/api/auth", params={"name": self.name})
        data = response.json()
        
        self.code = data["code"]
        self.ping_interval = data.get("pingEverySeconds", 5)
        
        print(f"🔑 Codice: {self.code}")
        return self.code
    
    def ping(self):
        visibility = "visible" if self.visible else "invisible"
        try:
            response = requests.get(
                f"{self.BASE_URL}/api/ping",
                params={"code": self.code, "visible": visibility},
                timeout=3
            )
            result = response.json()
            
            if not result.get("ok"):
                self.authenticate()
                return False
            
            return True
        except Exception as e:
            print(f"⚠️ Ping error: {e}")
            return False
    
    def ping_loop(self):
        while self._running:
            self.ping()
            time.sleep(self.ping_interval)
    
    def get_enemies_with_scores(self) -> List[Dict]:
        """Ottiene lista nemici con i loro punti"""
        try:
            response = requests.get(
                f"{self.BASE_URL}/api/players", 
                params={"code": self.code},
                timeout=3
            )
            players = response.json().get("players", [])
            
            # Filtra nemici visibili e ordina per punti (decrescente)
            enemies = [
                {
                    "name": p["name"],
                    "score": p.get("score", 0),
                    "kills": p.get("kills", 0),
                    "deaths": p.get("deaths", 0)
                }
                for p in players 
                if p["name"] != self.name and p.get("visible", False)
            ]
            
            # Ordina per punti decrescenti (priorità ai più forti)
            enemies.sort(key=lambda x: x["score"], reverse=True)
            
            return enemies
            
        except Exception as e:
            print(f"⚠️ Error getting enemies: {e}")
            return []
    
    def fire_at(self, target: str):
        """Spara un singolo colpo"""
        try:
            requests.get(
                f"{self.BASE_URL}/api/fire",
                params={"code": self.code, "target": target},
                timeout=2
            )
        except Exception as e:
            # Ignora errori per mantenere velocità
            pass
    
    def rapid_fire(self, target: str, shots: int):
        """Spara rapidamente a un target"""
        for _ in range(shots):
            if not self._running:
                break
            self.fire_at(target)
            if self.fire_delay > 0:
                time.sleep(self.fire_delay)
    
    def fire_volley_at_target(self, enemy: Dict):
        """Spara una raffica a un nemico specifico"""
        target_name = enemy["name"]
        target_score = enemy["score"]
        
        print(f"🎯 Target: {target_name} (Score: {target_score})")
        self.rapid_fire(target_name, self.shots_per_target)
        print(f"💀 Completato attacco su {target_name}")
    
    def fire_loop(self):
        """Loop principale di attacco con threading parallelo"""
        while self._running:
            enemies = self.get_enemies_with_scores()
            
            if not enemies:
                print("👻 Nessun nemico visibile")
                time.sleep(2)
                continue
            
            # Mostra priorità
            print(f"\n🔥 {len(enemies)} nemici identificati:")
            for i, enemy in enumerate(enemies[:3]):  # Top 3
                print(f"  {i+1}. {enemy['name']} - {enemy['score']} pts")
            
            # Attacca in parallelo (priorità ai primi target)
            futures = []
            for enemy in enemies:
                if not self._running:
                    break
                future = self.executor.submit(self.fire_volley_at_target, enemy)
                futures.append(future)
            
            # Aspetta che tutti i thread finiscano prima del prossimo ciclo
            for future in futures:
                if not self._running:
                    break
                future.result()
            
            # Breve pausa prima del prossimo ciclo
            time.sleep(0.5)
    
    def start(self):
        """Avvia il bot"""
        print(f"🤖 Avvio {self.name}...")
        print(f"⚙️  Config: {self.shots_per_target} colpi/target, {self.max_workers} thread paralleli")
        print(f"⚡ Fire rate: ~{int(1/self.fire_delay)} colpi/secondo per thread" if self.fire_delay > 0 else "⚡ Fire rate: MASSIMO")
        
        self.authenticate()
        self._running = True
        
        # Avvia ping thread
        ping_thread = threading.Thread(target=self.ping_loop, daemon=True)
        ping_thread.start()
        
        try:
            self.fire_loop()
        except KeyboardInterrupt:
            print("\n⏹️  Interruzione...")
            self.stop()
    
    def stop(self):
        """Ferma il bot"""
        print("🛑 Arresto bot...")
        self._running = False
        self.executor.shutdown(wait=False)
        print("✅ Bot arrestato")


if __name__ == "__main__":
    # Configurazione AGGRESSIVA
    bot = GameBotTurbo(
        name="sergio_turbo", 
        visible=True,  # Cambia a False per essere invisibile
        shots_per_target=30,  # Più colpi per target
        max_workers=8,  # Più thread paralleli = più veloce
        fire_delay=0.001  # 5ms tra colpi = ~200 colpi/sec per thread
    )
    bot.start()