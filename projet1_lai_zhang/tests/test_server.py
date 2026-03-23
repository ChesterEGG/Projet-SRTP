import os
import sys
import tempfile
import socket
sys.path.append("src")
import server
from packet import Packet

#faux socket pour test
class FakeSocket:
    def __init__(self, rep):
        self.rep = rep
        self.sent = []

    def sendto(self, data, addr):
        self.sent.append((data, addr))

    def recvfrom(self, n):
        x = self.rep.pop(0)
        if isinstance(x, Exception):
            raise x
        return x

    def settimeout(self, t):
        pass

    def bind(self, addr):
        self.bound = addr

    def close(self):
        pass

#creer un ack
def make_ack(seq):
    return Packet(2, 0, seq, 0, b"").pack()

#créer une requet get
def make_get(path):
    return Packet(1, 0, 0, 0, ("GET " + path).encode()).pack()

#test si elle n'existe pas
def test_fichier_inexistant():
    sock = FakeSocket([])
    addr = ("::1", 9999)

    server.send_file(sock, addr, "pas_la.txt", 32)
    assert len(sock.sent) == 1
    p = Packet.unpack(sock.sent[0][0])
    assert p.seqnum == 0
    assert p.payload == b""

def test_petit_fichier():
    addr = ("::1", 9999)
    sock = FakeSocket([
        (make_ack(1), addr),
        (make_ack(2), addr),
    ])
    f = tempfile.NamedTemporaryFile(delete=False)
    f.write(b"hello")
    f.close()
    try:
        server.send_file(sock, addr, f.name, 32)
        payloads = []
        for data, a in sock.sent:
            p = Packet.unpack(data)
            payloads.append(p.payload)

        assert b"hello" in payloads
        assert b"" in payloads
    finally:
        os.remove(f.name)

#test si star server appel send file
def test_start_server_simple():
    called = {"ok": False, "addr": None}

    def fake_send(sock, addr, path, window):
        called["ok"] = True
        called["addr"] = addr
        raise KeyboardInterrupt()

    class FakeSock:
        def __init__(self):
            self.n = 0

        def bind(self, addr):
            self.bound = addr

        def settimeout(self, t):
            pass

        def recvfrom(self, n):
            if self.n == 0:
                self.n += 1
                return (make_get("/x"), ("::1", 1234))
            raise KeyboardInterrupt()

        def close(self):
            pass

    fake = FakeSock()
    old_socket = server.socket.socket
    old_send = server.send_file
    old_argv = sys.argv

    server.socket.socket = lambda *a: fake
    server.send_file = fake_send
    sys.argv = ["server.py", "::1", "1234"]

    try:
        server.start_server()
    except KeyboardInterrupt:
        pass
    server.socket.socket = old_socket
    server.send_file = old_send
    sys.argv = old_argv

    assert called["ok"] == True
    assert called["addr"] == ("::1", 1234)