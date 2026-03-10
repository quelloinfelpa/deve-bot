import requests
from time import sleep
from threading import Thread

BASE_URL = 'https://sososisi.isonlab.net'

class DeveBot():
    def __init__(self):
        self.name = 'TangiBot'
        self.code = self.auth(self.name)
        self.visible = False

    #GET /api/auth?name=Mario
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
    
    


DeveBot()