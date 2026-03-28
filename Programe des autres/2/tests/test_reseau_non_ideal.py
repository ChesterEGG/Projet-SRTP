"""
tests/test_reseau_non_ideal.py

Tests black-box pour l'étape 5 : réseau non-idéal.

Architecture :
    Client → Proxy (port proxy) → Serveur (port serveur)
           ←                   ←

Le proxy s'intercale entre le client et le serveur.
Il peut introduire : pertes, corruption, désordre, latence.
"""

import os
import sys
import subprocess
import time
import filecmp
import random
import socket
import threading
import pytest

PYTHON        = sys.executable
SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'src', 'server.py')
CLIENT_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'src', 'client.py')

SERVER_HOST = "::1"


# ============================================================
# Proxy UDP
# ============================================================

class UDPProxy:
    """
    Proxy UDP IPv6 qui s'intercale entre client et serveur.

    Paramètres configurables :
        loss_rate      : probabilité de perdre un paquet (0.0 à 1.0)
        corrupt_rate   : probabilité de corrompre un octet (0.0 à 1.0)
        delay_range    : (min_ms, max_ms) délai ajouté à chaque paquet
        reorder_rate   : probabilité de retarder un paquet pour simuler le désordre
    """

    def __init__(self, proxy_port, server_port,
                 loss_rate=0.0, corrupt_rate=0.0,
                 delay_range=(0, 0), reorder_rate=0.0):
        self.proxy_port   = proxy_port
        self.server_port  = server_port
        self.loss_rate    = loss_rate
        self.corrupt_rate = corrupt_rate
        self.delay_range  = delay_range
        self.reorder_rate = reorder_rate

        self.client_addr  = None   # adresse du client (découverte au 1er paquet)
        self.running      = False
        self.thread       = None

        # Socket côté client (écoute les paquets du client)
        self.sock_client = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        self.sock_client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock_client.bind((SERVER_HOST, proxy_port))
        self.sock_client.settimeout(0.1)

        # Socket côté serveur (transmet au serveur et reçoit ses réponses)
        self.sock_server = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        self.sock_server.settimeout(0.1)

    def _should_drop(self):
        return random.random() < self.loss_rate

    def _maybe_corrupt(self, data):
        if random.random() < self.corrupt_rate:
            data = bytearray(data)
            idx = random.randint(0, len(data) - 1)
            data[idx] ^= 0xFF
            return bytes(data)
        return data

    def _get_delay(self):
        lo, hi = self.delay_range
        if hi == 0:
            return 0
        return random.uniform(lo, hi) / 1000.0  # convertit ms → secondes

    def _send_delayed(self, sock, data, addr):
        """Envoie un paquet après un délai optionnel (dans un thread séparé)."""
        delay = self._get_delay()
        if delay > 0:
            def _send():
                time.sleep(delay)
                try:
                    sock.sendto(data, addr)
                except Exception:
                    pass
            threading.Thread(target=_send, daemon=True).start()
        else:
            try:
                sock.sendto(data, addr)
            except Exception:
                pass

    def _loop(self):
        """Boucle principale du proxy, tourne dans un thread dédié."""
        while self.running:
            # --- Paquets Client → Serveur ---
            try:
                data, addr = self.sock_client.recvfrom(4096)
                self.client_addr = addr

                if not self._should_drop():
                    data = self._maybe_corrupt(data)
                    self._send_delayed(
                        self.sock_server, data,
                        (SERVER_HOST, self.server_port, 0, 0)
                    )
            except socket.timeout:
                pass
            except Exception:
                pass

            # --- Paquets Serveur → Client ---
            try:
                data, _ = self.sock_server.recvfrom(4096)
                if self.client_addr and not self._should_drop():
                    data = self._maybe_corrupt(data)
                    self._send_delayed(self.sock_client, data, self.client_addr)
            except socket.timeout:
                pass
            except Exception:
                pass

    def start(self):
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        try:
            self.sock_client.close()
        except Exception:
            pass
        try:
            self.sock_server.close()
        except Exception:
            pass


# ============================================================
# Helpers
# ============================================================

def launch_server(tmp_path, port):
    proc = subprocess.Popen(
        [PYTHON, SERVER_SCRIPT, SERVER_HOST, str(port), "--root", str(tmp_path)],
        stderr=subprocess.DEVNULL
    )
    time.sleep(0.5)
    return proc


def run_client(tmp_path, filename, port, client_timeout=60):
    fichier_recu = tmp_path / "resultat.bin"
    proc = subprocess.Popen(
        [PYTHON, CLIENT_SCRIPT,
         f"http://[::1]:{port}/{filename}",
         "--save", str(fichier_recu)],
        stderr=subprocess.DEVNULL
    )
    proc.wait(timeout=client_timeout)
    return proc, fichier_recu


def make_source(tmp_path, size_bytes):
    """Crée un fichier source aléatoire de size_bytes octets."""
    source = tmp_path / "source.bin"
    source.write_bytes(os.urandom(size_bytes))
    return source


# ============================================================
# Tests
# ============================================================

def test_pertes_paquets_data(tmp_path):
    """
    30% des paquets DATA (client→serveur ET serveur→client) sont perdus.
    Le serveur doit retransmettre, le transfert doit quand même réussir.
    """
    source = make_source(tmp_path, 50 * 1024)

    srv   = launch_server(tmp_path, port=9100)
    proxy = UDPProxy(proxy_port=9200, server_port=9100, loss_rate=0.3)
    proxy.start()

    try:
        proc, recu = run_client(tmp_path, "source.bin", port=9200, client_timeout=60)
        assert proc.returncode == 0, "Le client a crashé"
        assert recu.exists(), "Fichier non sauvegardé"
        assert filecmp.cmp(source, recu, shallow=False), "Corruption de données"
    finally:
        proxy.stop()
        srv.terminate(); srv.wait()


def test_pertes_paquets_ack(tmp_path):
    """
    40% des ACKs sont perdus (simulé en mettant un taux de perte élevé
    sur tous les paquets — le serveur devra retransmettre beaucoup).
    """
    source = make_source(tmp_path, 20 * 1024)

    srv   = launch_server(tmp_path, port=9101)
    proxy = UDPProxy(proxy_port=9201, server_port=9101, loss_rate=0.4)
    proxy.start()

    try:
        proc, recu = run_client(tmp_path, "source.bin", port=9201, client_timeout=60)
        assert proc.returncode == 0
        assert filecmp.cmp(source, recu, shallow=False)
    finally:
        proxy.stop()
        srv.terminate(); srv.wait()


def test_corruption(tmp_path):
    """
    20% des paquets ont un octet corrompu.
    Les CRC doivent détecter la corruption, les paquets corrompus sont ignorés,
    le serveur retransmet après timeout.
    """
    source = make_source(tmp_path, 20 * 1024)

    srv   = launch_server(tmp_path, port=9102)
    proxy = UDPProxy(proxy_port=9202, server_port=9102, corrupt_rate=0.2)
    proxy.start()

    try:
        proc, recu = run_client(tmp_path, "source.bin", port=9202, client_timeout=60)
        assert proc.returncode == 0
        assert filecmp.cmp(source, recu, shallow=False)
    finally:
        proxy.stop()
        srv.terminate(); srv.wait()


def test_latence_elevee(tmp_path):
    """
    Latence fixe de 400ms sur chaque paquet (RTT ~800ms).
    Le timeout de 1.5s doit être suffisant pour ne pas retransmettre inutilement.
    """
    source = make_source(tmp_path, 10 * 1024)

    srv   = launch_server(tmp_path, port=9103)
    proxy = UDPProxy(proxy_port=9203, server_port=9103, delay_range=(400, 400))
    proxy.start()

    try:
        proc, recu = run_client(tmp_path, "source.bin", port=9203, client_timeout=60)
        assert proc.returncode == 0
        assert filecmp.cmp(source, recu, shallow=False)
    finally:
        proxy.stop()
        srv.terminate(); srv.wait()


def test_desordre(tmp_path):
    """
    Délai aléatoire entre 0 et 500ms = les paquets arrivent dans le désordre.
    Le buffer de réception du client doit les réordonner correctement.
    """
    source = make_source(tmp_path, 20 * 1024)

    srv   = launch_server(tmp_path, port=9104)
    proxy = UDPProxy(proxy_port=9204, server_port=9104, delay_range=(0, 500))
    proxy.start()

    try:
        proc, recu = run_client(tmp_path, "source.bin", port=9204, client_timeout=60)
        assert proc.returncode == 0
        assert filecmp.cmp(source, recu, shallow=False)
    finally:
        proxy.stop()
        srv.terminate(); srv.wait()


def test_combinaison(tmp_path):
    """
    Scénario réaliste combinant toutes les conditions :
    - 20% de pertes
    - 10% de corruption
    - Latence variable entre 50ms et 300ms (désordre inclus)
    C'est le test le plus dur, timeout généreux à 120s.
    """
    source = make_source(tmp_path, 20 * 1024)

    srv   = launch_server(tmp_path, port=9105)
    proxy = UDPProxy(
        proxy_port=9205, server_port=9105,
        loss_rate=0.2, corrupt_rate=0.1,
        delay_range=(50, 300)
    )
    proxy.start()

    try:
        proc, recu = run_client(tmp_path, "source.bin", port=9205, client_timeout=120)
        assert proc.returncode == 0
        assert filecmp.cmp(source, recu, shallow=False)
    finally:
        proxy.stop()
        srv.terminate(); srv.wait()