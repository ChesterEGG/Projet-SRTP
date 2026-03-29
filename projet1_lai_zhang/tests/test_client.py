import os
import sys
import tempfile
import pytest
import socket
sys.path.append("src")
import client
from packet import Packet


#faux socket pour test
class FakeSocket:
    def __init__(self, rep):
        self.rep = rep
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recvfrom(self, n):
        if not self.rep:
            # Simule une attente infinie ou une fin de flux
            raise socket.timeout
        return self.rep.pop(0)

    def settimeout(self, t):
        pass

    def close(self):
        pass

#créer un paquet data
def make_data(seq, txt):
    if type(txt) == str:
        txt = txt.encode()
    return Packet(1, 32, seq, 0, txt).pack()

#créer un paquet vide
def make_fin(seq):
    return Packet(1, 32, seq, 0, b"").pack()


def test_mauvais_scheme():
    old = sys.argv
    sys.argv = ["client.py", "abc://test:1234/x"]
    try:
        with pytest.raises(SystemExit):
            client.start_client()
    finally:
        sys.argv = old

#test 1paquet data puis fin
def test_client_simple():
    addr = ("::1", 8000)
    rep = [
        (make_data(0, "hello"), addr),
        (make_fin(1), addr),
    ]

    fake = FakeSocket(rep)
    old_socket = client.socket.socket
    old_argv = sys.argv

    f = tempfile.NamedTemporaryFile(delete=False)
    f.close()

    client.socket.socket = lambda *a: fake
    #hostname = test, port=1234, path=/x
    sys.argv = ["client.py", "http://test:1234/x", "--save", f.name]
    client.start_client()

    data = open(f.name, "rb").read()
    assert data == b"hello"

    #+ 2 ACK
    assert len(fake.sent) == 3

    client.socket.socket = old_socket
    sys.argv = old_argv
    os.remove(f.name)

def test_client_url_invalide():
    old = sys.argv
    sys.argv = ["client.py", "jsp"]
    with pytest.raises(SystemExit):
        client.start_client()
    sys.argv = old


def test_client_desordre():
    """
    Vérifie que le client gère les paquets arrivant dans le désordre.
    On envoie le segment 1 avant le segment 0.
    """
    addr = ("::1", 8000)
    rep = [
        (make_data(1, " world"), addr),
        (make_data(0, "hello"), addr),
        (make_fin(2), addr),
    ]

    fake = FakeSocket(rep)
    old_socket = client.socket.socket

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        f_name = tmp.name

    try:
        client.socket.socket = lambda *a: fake
        sys.argv = ["client.py", "http://localhost:8000/order.txt", "--save", f_name]
        client.start_client()

        with open(f_name, "rb") as f:
            assert f.read() == b"hello world"
    finally:
        client.socket.socket = old_socket
        if os.path.exists(f_name):
            os.remove(f_name)


def test_client_doublon():
    """Vérifie que le client ignore les paquets déjà reçus."""
    addr = ("::1", 8000)
    # On envoie le Seq 0 deux fois
    rep = [
        (make_data(0, "unique"), addr),
        (make_data(0, "unique"), addr),
        (make_fin(1), addr),
    ]

    fake = FakeSocket(rep)
    old_socket = client.socket.socket

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        f_name = tmp.name

    try:
        client.socket.socket = lambda *a: fake
        sys.argv = ["client.py", "http://localhost:8000/dup.txt", "--save", f_name]
        client.start_client()

        with open(f_name, "rb") as f:
            assert f.read() == b"unique"
    finally:
        client.socket.socket = old_socket
        if os.path.exists(f_name):
            os.remove(f_name)