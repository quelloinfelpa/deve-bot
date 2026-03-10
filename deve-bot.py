import requests
from time import sleep
from threading import Thread

BASE_URL = 'https://sososisi.isonlab.net'

class DeveBot():
    def __init__(self):
        self.name = 'TangiBot'
        self.code = self.auth(self.name)
        self.visible = False

    def shoot(self):
        players = self.get_players()
        if len(players) > 0:
            if not self.visible:
                self.change_visibilty()
            target = players[0]['name']
            url = BASE_URL + '/api/fire?code=' + self.code + '&target=' + target
            res = requests.get(url)
            if self.visible:
                self.change_visibilty() #diventa invisibile
            return res.json()
        else:
            print('No players to shoot at')
            return None
    def auth(self, name):
        url = BASE_URL + '/api/auth?name=' + name
        res = requests.get(url)
        return res.json()

    def change_visibilty(self):
        self.visible = not self.visible
        url = BASE_URL + '/api/ping?code=' + self.code + '&visible=' + ('visible' if self.visible else 'invisible') #if else in una sola riga (lo abbiamo fatto no?)
        res = requests.get(url)
        return res.json()

    def ping_keep_alive(self):
        url = BASE_URL + '/api/ping?code=' + self.code
        res = requests.get(url)
        return res.json()
    
    def get_players(self):
        url = BASE_URL + '/api/players?code=' + self.code
        res = requests.get(url)
        return res.json()
    

if __name__ == "__main__":
    bot = DeveBot()
    bot.game()

#shoot: prende lista utenti visibili, si setta visibile, spara al primo, si setta invisibile
'''
#per autenticarsi, restituisce un codice da usare per il ping
GET /api/auth?name=Mario
{
  "ok": true,
  "name": "Mario",
  "code": "AB12CD34",
  "pingEverySeconds": 5
}

#ogni 5 secondi da fare altrimenti si muore (thread che lo fa in automatico)
GET /api/ping?code=AB12CD34
#per diventare visibili
GET /api/ping?code=AB12CD34&visible=visible
#per diventare invisibili
GET /api/ping?code=AB12CD34&visible=invisible
{
  "ok": true,
  "name": "Mario",
  "visible": true,
  "nextPingAt": "2026-03-09T22:00:05.000Z"
}

#lista bot autenticati
GET /api/players?code=AB12CD34

#spara
GET /api/fire?code=AB12CD34&target=Luisa
'''