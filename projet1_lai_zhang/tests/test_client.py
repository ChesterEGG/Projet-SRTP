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
        return self.rep.pop(0)

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