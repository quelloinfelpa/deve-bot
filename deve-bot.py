import requests
import time
import threading
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime


# ─────────────────────────────────────────────
#  SESSION
# ─────────────────────────────────────────────

SESSION_FILE = "bot_session.json"


@dataclass
class SessionStats:
    total_shots_fired: int = 0
    total_kills: int = 0
    sessions_started: int = 0
    last_login: str = ""
    uptime_seconds: float = 0.0


@dataclass
class Session:
    name: str
    code: str
    ping_interval: int
    created_at: str
    stats: SessionStats = field(default_factory=SessionStats)

    def save(self, path: str = SESSION_FILE):
        data = {
            "name": self.name,
            "code": self.code,
            "ping_interval": self.ping_interval,
            "created_at": self.created_at,
            "stats": asdict(self.stats),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"💾 Sessione salvata ({path})")

    @staticmethod
    def load(path: str = SESSION_FILE) -> Optional["Session"]:
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            stats = SessionStats(**data.get("stats", {}))
            return Session(
                name=data["name"],
                code=data["code"],
                ping_interval=data.get("ping_interval", 5),
                created_at=data.get("created_at", ""),
                stats=stats,
            )
        except Exception as e:
            print(f"⚠️  Impossibile caricare sessione: {e}")
            return None

    def update_stats(self, shots: int = 0, kills: int = 0):
        self.stats.total_shots_fired += shots
        self.stats.total_kills += kills

    def print_stats(self):
        s = self.stats
        print(
            f"\n📊 Statistiche sessione:"
            f"\n   Colpi totali  : {s.total_shots_fired}"
            f"\n   Kill totali   : {s.total_kills}"
            f"\n   Sessioni avv. : {s.sessions_started}"
            f"\n   Ultimo login  : {s.last_login}"
        )


# ─────────────────────────────────────────────
#  TARGETING
# ─────────────────────────────────────────────

@dataclass
class Enemy:
    name: str
    score: int
    kills: int
    deaths: int

    @property
    def threat_score(self) -> float:
        """
        Punteggio composito che bilancia punti, kill rate e fragilità.
        Priorità assoluta al leader (score), ma considera anche kd ratio.
        """
        kd = self.kills / max(self.deaths, 1)
        # 70% peso ai punti grezzi, 30% al kd ratio normalizzato
        return self.score * 0.70 + (kd * 100) * 0.30

    def __repr__(self):
        kd = self.kills / max(self.deaths, 1)
        return (
            f"{self.name:20s} | score={self.score:6d} "
            f"| k/d={kd:.2f} | threat={self.threat_score:.1f}"
        )


class SmartTargeter:
    """
    Gestisce la selezione e il tracciamento del target principale.
    Aggiorna il target in tempo reale se la classifica cambia.
    """

    def __init__(self, recheck_after_shots: int = 15):
        self.current_target: Optional[Enemy] = None
        self.shots_on_target: int = 0
        self.recheck_after_shots = recheck_after_shots
        self._lock = threading.Lock()

    def select_target(self, enemies: List[Enemy]) -> Optional[Enemy]:
        if not enemies:
            return None
        # Seleziona il nemico con threat_score massimo
        return max(enemies, key=lambda e: e.threat_score)

    def update(self, enemies: List[Enemy]) -> Optional[Enemy]:
        """
        Aggiorna il target corrente:
        - Cambio forzato se il punteggio del leader supera quello attuale
          di un margine significativo (>10%)
        - Cambio normale dopo recheck_after_shots colpi
        """
        with self._lock:
            best = self.select_target(enemies)
            if best is None:
                self.current_target = None
                return None

            if self.current_target is None:
                self._switch(best, "Primo target")
                return self.current_target

            current_still_alive = any(
                e.name == self.current_target.name for e in enemies
            )

            if not current_still_alive:
                self._switch(best, "Target eliminato/invisibile")
                return self.current_target

            # Cambio immediato se il nuovo leader è molto più forte
            margin = best.threat_score - self.current_target.threat_score
            if margin > self.current_target.threat_score * 0.10:
                self._switch(best, f"Nuovo leader (+{margin:.0f} pts threat)")
                return self.current_target

            # Ricalibrazione periodica
            if self.shots_on_target >= self.recheck_after_shots:
                updated_current = next(
                    (e for e in enemies if e.name == self.current_target.name),
                    None,
                )
                if updated_current:
                    self.current_target = updated_current
                self.shots_on_target = 0

            return self.current_target

    def register_shot(self):
        with self._lock:
            self.shots_on_target += 1

    def _switch(self, new_target: Enemy, reason: str):
        old = self.current_target.name if self.current_target else "—"
        self.current_target = new_target
        self.shots_on_target = 0
        print(f"🎯 TARGET → {new_target.name}  [{reason}]  (era: {old})")


# ─────────────────────────────────────────────
#  BOT
# ─────────────────────────────────────────────

class GameBotTurbo:

    BASE_URL = "https://sososisi.isonlab.net"
    MAX_AUTH_RETRIES = 5

    def __init__(
        self,
        name: str,
        visible: bool = True,
        shots_per_burst: int = 30,
        max_workers: int = 8,
        fire_delay: float = 0.001,
        recheck_after_shots: int = 15,
        session_path: str = SESSION_FILE,
    ):
        self.name = name
        self.visible = visible
        self.shots_per_burst = shots_per_burst
        self.max_workers = max_workers
        self.fire_delay = fire_delay
        self.session_path = session_path

        self._session: Optional[Session] = None
        self._running = False
        self._start_time: float = 0.0
        self._shots_this_run: int = 0

        self.targeter = SmartTargeter(recheck_after_shots=recheck_after_shots)
        self.executor = ThreadPoolExecutor(max_workers=max_workers)

    # ── Auth / Session ────────────────────────

    def authenticate(self, retry: bool = True) -> str:
        """
        Autentica il bot:
        1. Prova a riusare la sessione salvata (stesso nome + code valido)
        2. Se fallisce, registra una nuova sessione con backoff esponenziale
        """
        # Prova a riusare sessione precedente
        existing = Session.load(self.session_path)
        if existing and existing.name == self.name:
            if self._validate_session(existing.code):
                print(f"✅ Sessione ripristinata  (code: {existing.code})")
                self._session = existing
                self._session.stats.sessions_started += 1
                self._session.stats.last_login = datetime.now().isoformat()
                self._session.save(self.session_path)
                return existing.code
            else:
                print("🔄 Sessione scaduta, re-autenticazione...")

        # Nuova autenticazione con retry esponenziale
        for attempt in range(1, self.MAX_AUTH_RETRIES + 1):
            try:
                response = requests.get(
                    f"{self.BASE_URL}/api/auth",
                    params={"name": self.name},
                    timeout=5,
                )
                data = response.json()
                code = data["code"]
                ping_interval = data.get("pingEverySeconds", 5)

                stats = SessionStats(
                    sessions_started=1,
                    last_login=datetime.now().isoformat(),
                )
                # Preserva stats storiche se stesso nome
                if existing and existing.name == self.name:
                    stats.total_shots_fired = existing.stats.total_shots_fired
                    stats.total_kills = existing.stats.total_kills
                    stats.sessions_started = existing.stats.sessions_started + 1

                self._session = Session(
                    name=self.name,
                    code=code,
                    ping_interval=ping_interval,
                    created_at=datetime.now().isoformat(),
                    stats=stats,
                )
                self._session.save(self.session_path)
                print(f"🔑 Nuovo codice: {code}")
                return code

            except Exception as e:
                wait = 2 ** attempt
                print(f"⚠️  Auth tentativo {attempt}/{self.MAX_AUTH_RETRIES}: {e}  (retry in {wait}s)")
                if attempt < self.MAX_AUTH_RETRIES:
                    time.sleep(wait)

        raise RuntimeError("❌ Autenticazione fallita dopo tutti i tentativi")

    def _validate_session(self, code: str) -> bool:
        """Verifica che un code sia ancora valido tramite ping"""
        try:
            r = requests.get(
                f"{self.BASE_URL}/api/ping",
                params={"code": code, "visible": "invisible"},
                timeout=3,
            )
            return r.json().get("ok", False)
        except Exception:
            return False

    @property
    def code(self) -> str:
        if self._session is None:
            raise RuntimeError("Bot non autenticato")
        return self._session.code

    # ── Ping ─────────────────────────────────

    def ping(self) -> bool:
        visibility = "visible" if self.visible else "invisible"
        try:
            r = requests.get(
                f"{self.BASE_URL}/api/ping",
                params={"code": self.code, "visible": visibility},
                timeout=3,
            )
            result = r.json()
            if not result.get("ok"):
                print("🔄 Ping fallito → re-autenticazione")
                self.authenticate()
                return False
            return True
        except Exception as e:
            print(f"⚠️  Ping error: {e}")
            return False

    def ping_loop(self):
        interval = self._session.ping_interval if self._session else 5
        while self._running:
            self.ping()
            time.sleep(interval)

    # ── Nemici ───────────────────────────────

    def get_enemies(self) -> List[Enemy]:
        try:
            r = requests.get(
                f"{self.BASE_URL}/api/players",
                params={"code": self.code},
                timeout=3,
            )
            players = r.json().get("players", [])
            enemies = [
                Enemy(
                    name=p["name"],
                    score=p.get("score", 0),
                    kills=p.get("kills", 0),
                    deaths=p.get("deaths", 0),
                )
                for p in players
                if p["name"] != self.name and p.get("visible", False)
            ]
            return enemies
        except Exception as e:
            print(f"⚠️  Errore get enemies: {e}")
            return []

    # ── Fire ─────────────────────────────────

    def fire_at(self, target: str):
        try:
            requests.get(
                f"{self.BASE_URL}/api/fire",
                params={"code": self.code, "target": target},
                timeout=2,
            )
            self._shots_this_run += 1
            if self._session:
                self._session.update_stats(shots=1)
            self.targeter.register_shot()
        except Exception:
            pass

    def burst_fire(self, target: str, shots: int):
        """Burst concentrato su un singolo target"""
        for _ in range(shots):
            if not self._running:
                break
            self.fire_at(target)
            if self.fire_delay > 0:
                time.sleep(self.fire_delay)

    # ── Fire Loop ────────────────────────────

    def fire_loop(self):
        """
        Loop intelligente:
        - Identifica il target prioritario (SmartTargeter)
        - Concentra il burst principale sul leader
        - Usa i thread rimanenti per colpi secondari sugli altri
        """
        save_interval = 30  # salva sessione ogni N secondi
        last_save = time.time()

        while self._running:
            enemies = self.get_enemies()

            if not enemies:
                print("👻 Nessun nemico visibile — attesa...")
                time.sleep(2)
                continue

            # Aggiorna / seleziona target
            primary = self.targeter.update(enemies)
            if primary is None:
                time.sleep(1)
                continue

            # Log classifica (top 3)
            print(f"\n{'─'*55}")
            print(f"{'🏆 CLASSIFICA':^55}")
            for i, e in enumerate(
                sorted(enemies, key=lambda x: x.threat_score, reverse=True)[:3], 1
            ):
                marker = "◀ PRIMARY" if e.name == primary.name else ""
                print(f"  {i}. {e}  {marker}")
            print(f"{'─'*55}")

            # ── Strategia di fuoco ──
            secondary_enemies = [e for e in enemies if e.name != primary.name]

            futures = []

            # Thread 1..N-1 → burst pesante sul leader
            primary_threads = max(1, self.max_workers - len(secondary_enemies))
            for _ in range(primary_threads):
                futures.append(
                    self.executor.submit(self.burst_fire, primary.name, self.shots_per_burst)
                )

            # Thread rimanenti → 1 burst leggero per distrazione/secondi
            for enemy in secondary_enemies[: self.max_workers - primary_threads]:
                light_shots = max(3, self.shots_per_burst // 5)
                futures.append(
                    self.executor.submit(self.burst_fire, enemy.name, light_shots)
                )

            for f in as_completed(futures):
                if not self._running:
                    break
                try:
                    f.result()
                except Exception as e:
                    print(f"⚠️  Thread error: {e}")

            # Salva sessione periodicamente
            if time.time() - last_save > save_interval:
                self._save_session_with_uptime()
                last_save = time.time()

            time.sleep(0.3)

    # ── Utilities ────────────────────────────

    def _save_session_with_uptime(self):
        if self._session:
            self._session.stats.uptime_seconds += time.time() - self._start_time
            self._session.save(self.session_path)

    # ── Start / Stop ─────────────────────────

    def start(self):
        print(f"\n{'═'*55}")
        print(f"  🤖  GameBotTurbo  —  {self.name}")
        print(f"{'═'*55}")
        print(f"  Burst principale : {self.shots_per_burst} colpi")
        print(f"  Thread paralleli : {self.max_workers}")
        rate = int(1 / self.fire_delay) if self.fire_delay > 0 else "∞"
        print(f"  Fire rate        : ~{rate} colpi/sec per thread")
        print(f"{'═'*55}\n")

        self.authenticate()
        self._running = True
        self._start_time = time.time()

        ping_thread = threading.Thread(target=self.ping_loop, daemon=True)
        ping_thread.start()

        try:
            self.fire_loop()
        except KeyboardInterrupt:
            print("\n⏹️  Interruzione richiesta...")
        finally:
            self.stop()

    def stop(self):
        print("\n🛑 Arresto bot...")
        self._running = False
        self.executor.shutdown(wait=False)
        self._save_session_with_uptime()
        if self._session:
            self._session.print_stats()
        print("✅ Bot arrestato")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    bot = GameBotTurbo(
        name="sergio_turbo",
        visible=True,
        shots_per_burst=100,
        max_workers=20,
        fire_delay=0.0001,        # ~1000 colpi/sec per thread
        recheck_after_shots=50,  # ricalibra il target ogni 15 colpi
        session_path="bot_session.json",
    )
    bot.start()