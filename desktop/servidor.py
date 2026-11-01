"""Waitress con socket reservado por el propio servidor y cierre explícito."""
import threading
from urllib.request import urlopen
from urllib.error import URLError
import time
import socket


class Servidor:
    def __init__(self, aplicacion, puerto=8000):
        from waitress import create_server
        reserva = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            try:
                reserva.bind(('127.0.0.1', puerto))
            except OSError as error:
                if error.errno not in (13, 98, 48, 10048, 10013):
                    raise
                reserva.bind(('127.0.0.1', 0))
            self.servidor = create_server(aplicacion, sockets=[reserva])
        except Exception:
            reserva.close()
            raise
        self.url = 'http://127.0.0.1:' + str(self.servidor.effective_port)
        self.hilo = threading.Thread(target=self.servidor.run, name='waitress', daemon=True)

    def iniciar(self):
        self.hilo.start()
        limite = time.monotonic() + 20
        while time.monotonic() < limite:
            try:
                with urlopen(self.url + '/login/', timeout=1) as respuesta:
                    if respuesta.status == 200:
                        return
            except (URLError, TimeoutError):
                time.sleep(.1)
        self.cerrar()
        raise RuntimeError('El servidor local no respondió a tiempo.')

    def cerrar(self):
        self.servidor.task_dispatcher.shutdown(timeout=30)
        self.servidor.close()
        # Retirar también canales keep-alive pertenecientes a este servidor.
        from waitress import wasyncore
        wasyncore.close_all(self.servidor._map)
        self.hilo.join(timeout=5)
