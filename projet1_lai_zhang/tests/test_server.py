import os
import sys
import tempfile
import socket
import pytest

sys.path.append("src")
import server
from packet import Packet

class StopServer(BaseException):
    pass

#faux socket pour test
class FakeSocket:
    def __init__(self, rep=None, mode = None):
        self.rep = rep if rep else []
        self.sent = []
        self.mode = mode
        self.timeout = None

    def sendto(self, data, addr):
        self.sent.append((data, addr))

        # Pour le test de la fenêtre : on arrête dès qu'on a rempli les 32 slots
        if self.mode == "window":
            data_packets = [d for d in self.sent if len(Packet.unpack(d[0]).payload) > 0]
            if len(data_packets) >= 32:
                raise StopServer("Fenêtre de 32 atteinte")

    def recvfrom(self, n):
        """
        Corriger par l'IA
        """
        # 1. S'il reste des ACKs dans la liste, on les donne au serveur
        if self.rep:
            return self.rep.pop(0)

        # 2. Si la liste est vide, on vérifie si on doit arrêter le serveur

        # Cas A : Test de Retransmission
        if self.mode == "retransmission":
            sent_seqs = [Packet.unpack(d[0]).seqnum for d in self.sent]
            # On s'arrête si le paquet 0 a été envoyé au moins 2 fois (original + retransmission)
            if sent_seqs.count(0) >= 2:
                raise StopServer("Retransmission détectée")

        # Cas B : Test de Wrap-around (Gros fichier)
        if self.mode == "wrap":
            # On vérifie si on a bien envoyé des paquets AU-DELÀ de l'index 2047
            # (Si on a au moins 2049 paquets dans 'sent', c'est qu'on a fait le tour)
            if len(self.sent) > 2048:
                raise StopServer("Wrap-around réussi : index > 2047 atteint")

        # 3. Sinon, on lève un timeout classique pour laisser le serveur
        # continuer sa boucle (et éventuellement retransmettre)
        raise socket.timeout

    def settimeout(self, t):
        self.timeout = t

    def bind(self, addr):
        self.bound = addr

    def close(self):
        pass

#creer un ack
def make_ack(seq):
    return Packet(2, 32, seq, 0, b"").pack()

#créer une requet get
def make_get(path):
    return Packet(1, 32, 0, 0, ("GET " + path).encode()).pack()

#test si elle n'existe pas
def test_fichier_inexistant():
    sock = FakeSocket([])
    addr = ("::1", 9999)

    server.send_file(sock, addr, "pas_la.txt", 32)
    assert len(sock.sent) == 1
    p = Packet.unpack(sock.sent[0][0])
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

def test_retransmission_sur_perte_ack():
    """Vérifie que le serveur renvoie le paquet après un timeout de 0.5s."""
    addr = ("::1", 9999)
    sock = FakeSocket([], mode="retransmission")

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"test retransmission")
        f_name = tmp.name

    try:
        with pytest.raises(StopServer):
            server.send_file(sock, addr, f_name, 32)

        sent_seqnums = [Packet.unpack(d[0]).seqnum for d in sock.sent]
        assert sent_seqnums.count(0) >= 2
    finally:
        if os.path.exists(f_name): os.remove(f_name)

def test_fenetre_glissante_stop_at_32():
    """Vérifie que le serveur ne dépasse pas la fenêtre de 32 sans ACK."""
    addr = ("::1", 9999)
    sock = FakeSocket([], mode="window")
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"A" * 1024 * 50) # Fichier de 50 paquets
        f_name = tmp.name

    try:
        with pytest.raises(StopServer):
            server.send_file(sock, addr, f_name, 32)
        nb_data = sum(1 for d in sock.sent if len(Packet.unpack(d[0]).payload) > 0)
        assert nb_data == 32
    finally:
        if os.path.exists(f_name): os.remove(f_name)


def test_integration_start_server():
    """Vérifie le dispatcher start_server."""
    called_params = {"path": None}

    def mock_send_file(sock, addr, path, window):
        called_params["path"] = path
        raise KeyboardInterrupt()

    old_send = server.send_file
    server.send_file = mock_send_file
    sock = FakeSocket([(make_get("test.txt"), ("::1", 1234))])

    old_socket = server.socket.socket
    server.socket.socket = lambda *a: sock
    sys.argv = ["server.py", "::1", "8080"]

    try:
        server.start_server()
    except KeyboardInterrupt:
        pass
    finally:
        server.send_file = old_send
        server.socket.socket = old_socket

    assert "test.txt" in called_params["path"]


def test_wrap_around_modulo_2048():
    """
    Vérifie que le serveur gère correctement le passage de Seq 2047 à Seq 0.
    Corriger par l'IA
    """
    addr = ("::1", 9999)
    # On fournit quelques ACKs pour aider le serveur à avancer
    responses = [
        (make_ack(2047), addr),
        (make_ack(0), addr),
        (make_ack(1), addr),
    ]

    # On active le mode "wrap"
    sock = FakeSocket(responses, mode="wrap")

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"A" * 1024 * 2050)
        f_name = tmp.name

    try:
        # LA CORRECTION EST ICI : on dit à pytest d'attendre l'exception StopServer
        with pytest.raises(StopServer):
            server.send_file(sock, addr, f_name, 32)

        # Si on arrive ici, c'est que StopServer a été levée, le test est réussi !
        # On peut faire une vérification supplémentaire sur les paquets envoyés
        sent_seqnums = [Packet.unpack(d[0]).seqnum for d in sock.sent]
        assert 0 in sent_seqnums
        assert 2047 in sent_seqnums
        # On vérifie que le 0 arrive bien APRÈS le 2047
        first_2047_idx = sent_seqnums.index(2047)
        try:
            wrap_around_0_idx = sent_seqnums.index(0, first_2047_idx)
            assert wrap_around_0_idx > first_2047_idx
            print(f"Succès : Le seq 0 a été trouvé à l'index {wrap_around_0_idx} après le seq 2047")
        except ValueError:
            pytest.fail("Le numéro de séquence 0 n'a pas été trouvé après le 2047 (échec du wrap-around)")

    finally:
        if os.path.exists(f_name):
            os.remove(f_name)