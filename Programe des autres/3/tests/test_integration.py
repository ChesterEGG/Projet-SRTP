import os
import sys
import time
import socket
import subprocess

import pytest

CODES_DIR = os.path.join(os.path.dirname(__file__), "..", "codes")
SERVER_PY = os.path.join(CODES_DIR, "server.py")
CLIENT_PY = os.path.join(CODES_DIR, "client.py")
PYTHON = sys.executable


def get_free_port():
    s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    s.bind(("::1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def launch_server(root, port):
    server = subprocess.Popen(
        [PYTHON, SERVER_PY, "::1", str(port), "--root", root],
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.4) 
    return server


def launch_client(port, file_path, save_path, timeout=20):
    result = subprocess.run(
        [PYTHON, CLIENT_PY, f"http://[::1]:{port}{file_path}", "--save", save_path],
        stderr=subprocess.DEVNULL,
        timeout=timeout,
    )
    return result.returncode


def write_file(path, data):
    with open(path, "wb") as f:
        f.write(data)


def read_file(path):
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def tmp_dir(tmp_path):
    return str(tmp_path)


def test_small_file_transfer(tmp_dir):
    # transfert d'un petit fichier texte: vérifie que le contenu reçu est identique
    content = b"Bonjour depuis le serveur SRTP"
    file_path = os.path.join(tmp_dir, "f.txt")
    write_file(file_path, content)

    port = get_free_port()
    server = launch_server(tmp_dir, port)

    try:
        save_path = os.path.join(tmp_dir, "received.txt")
        code = launch_client(port, "/f.txt", save_path)

        assert code == 0
        assert read_file(save_path) == content
    finally:
        server.terminate()
        server.wait()


def test_big_file_transfer(tmp_dir):
    # transfert d'un fichier binaire aléatoire de 5000 octets : vérifie l'intégrité complète
    content = os.urandom(5000)
    file_path = os.path.join(tmp_dir, "f.bin")
    write_file(file_path, content)

    port = get_free_port()
    server = launch_server(tmp_dir, port)

    try:
        save_path = os.path.join(tmp_dir, "received.bin")
        code = launch_client(port, "/f.bin", save_path)

        assert code == 0
        assert read_file(save_path) == content
    finally:
        server.terminate()
        server.wait()


def test_missing_file(tmp_dir):
    # requête d'un fichier inexistant : le client doit terminer sans erreur et écrire un fichier vide
    port = get_free_port()
    server = launch_server(tmp_dir, port)

    try:
        save_path = os.path.join(tmp_dir, "received.bin")
        code = launch_client(port, "/file_that_does_not_exist.txt", save_path)

        assert code == 0
        assert read_file(save_path) == b""
    finally:
        server.terminate()
        server.wait()


def test_two_transfers_in_a_row(tmp_dir):
    # deux transferts successifs sur le même serveur : vérifie que le serveur reste opérationnel entre les deux
    content1 = b"premier fichier"
    content2 = b"deuxieme fichier"

    write_file(os.path.join(tmp_dir, "f1.txt"), content1)
    write_file(os.path.join(tmp_dir, "f2.txt"), content2)

    port = get_free_port()
    server = launch_server(tmp_dir, port)

    try:
        save1 = os.path.join(tmp_dir, "r1.txt")
        save2 = os.path.join(tmp_dir, "r2.txt")

        code1 = launch_client(port, "/f1.txt", save1)
        code2 = launch_client(port, "/f2.txt", save2)

        assert code1 == 0
        assert code2 == 0
        assert read_file(save1) == content1
        assert read_file(save2) == content2
    finally:
        server.terminate()
        server.wait()