import os
import sys
import subprocess
import time
import filecmp
import pytest

PYTHON = sys.executable 

SERVER_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'src', 'server.py')
CLIENT_SCRIPT = os.path.join(os.path.dirname(__file__), '..', 'src', 'client.py')

def launch_server(tmp_path, port):
    """Lance le serveur en tâche de fond et attend qu'il soit prêt."""
    proc = subprocess.Popen(
        [PYTHON, SERVER_SCRIPT, "::1", str(port), "--root", str(tmp_path)],
        stderr=subprocess.DEVNULL
    )
    time.sleep(0.5)
    return proc


def run_client(tmp_path, filename, port, client_timeout=20):
    """Lance le client et attend qu'il termine. Retourne (process, chemin_fichier_recu)."""
    fichier_recu = tmp_path / "resultat.bin"
    proc = subprocess.Popen(
        [PYTHON, CLIENT_SCRIPT,
         f"http://[::1]:{port}/{filename}",
         "--save", str(fichier_recu)],
        stderr=subprocess.DEVNULL
    )
    proc.wait(timeout=client_timeout)
    return proc, fichier_recu



def test_transfert_50ko(tmp_path):
    """Transfert nominal d'un fichier de 50 Ko."""
    source = tmp_path / "source.bin"
    source.write_bytes(os.urandom(50 * 1024))

    srv = launch_server(tmp_path, port=8080)
    try:
        proc, recu = run_client(tmp_path, "source.bin", port=8080)
        assert proc.returncode == 0, "Le client a crashé"
        assert recu.exists(), "Le fichier n'a pas été sauvegardé"
        assert filecmp.cmp(source, recu, shallow=False), "Corruption de données"
    finally:
        srv.terminate(); srv.wait()


def test_transfert_fichier_vide(tmp_path):
    """Transfert d'un fichier vide (0 octet)."""
    source = tmp_path / "vide.bin"
    source.write_bytes(b'')

    srv = launch_server(tmp_path, port=8081)
    try:
        proc, recu = run_client(tmp_path, "vide.bin", port=8081)
        assert proc.returncode == 0
        assert recu.exists()
        assert recu.read_bytes() == b''
    finally:
        srv.terminate(); srv.wait()


def test_transfert_exactement_1_paquet(tmp_path):
    """Fichier de exactement 1024 octets = 1 seul paquet DATA."""
    source = tmp_path / "un_paquet.bin"
    source.write_bytes(os.urandom(1024))

    srv = launch_server(tmp_path, port=8082)
    try:
        proc, recu = run_client(tmp_path, "un_paquet.bin", port=8082)
        assert proc.returncode == 0
        assert filecmp.cmp(source, recu, shallow=False)
    finally:
        srv.terminate(); srv.wait()


def test_transfert_2_paquets(tmp_path):
    """Fichier de 1025 octets = 2 paquets, teste le passage au 2ème paquet."""
    source = tmp_path / "deux_paquets.bin"
    source.write_bytes(os.urandom(1025))

    srv = launch_server(tmp_path, port=8083)
    try:
        proc, recu = run_client(tmp_path, "deux_paquets.bin", port=8083)
        assert proc.returncode == 0
        assert filecmp.cmp(source, recu, shallow=False)
    finally:
        srv.terminate(); srv.wait()


def test_fichier_inexistant(tmp_path):
    """Le serveur renvoie un paquet vide si le fichier n'existe pas."""
    srv = launch_server(tmp_path, port=8084)
    try:
        proc, recu = run_client(tmp_path, "nexiste_pas.bin", port=8084)
        assert proc.returncode == 0
        assert recu.exists()
        assert recu.read_bytes() == b''
    finally:
        srv.terminate(); srv.wait()


def test_transfert_500ko_wraparound(tmp_path):
    """
    Fichier de 500 Ko (~500 paquets).
    Teste le wrap-around du seqnum (2047 -> 0) car 500 > 2047/4 paquets environ.
    """
    source = tmp_path / "grand.bin"
    source.write_bytes(os.urandom(500 * 1024))

    srv = launch_server(tmp_path, port=8085)
    try:
        proc, recu = run_client(tmp_path, "grand.bin", port=8085, client_timeout=60)
        assert proc.returncode == 0
        assert filecmp.cmp(source, recu, shallow=False)
    finally:
        srv.terminate(); srv.wait()


def test_transfert_1_octet(tmp_path):
    """Cas limite : fichier d'un seul octet."""
    source = tmp_path / "un_octet.bin"
    source.write_bytes(b'\x42')

    srv = launch_server(tmp_path, port=8086)
    try:
        proc, recu = run_client(tmp_path, "un_octet.bin", port=8086)
        assert proc.returncode == 0
        assert recu.read_bytes() == b'\x42'
    finally:
        srv.terminate(); srv.wait()