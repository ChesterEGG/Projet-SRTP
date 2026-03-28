import os
import threading
import time
import socket
import random
import pytest
from src.server import run_server
from src.client import run_client

# Classe pour simuler les arguments normalement passés dans le terminal (via argparse)
class MockArgs:
    def __init__(self, hostname, port, root, save=None, servername=None):
        self.hostname = hostname
        self.port = port
        self.root = root
        self.save = save
        self.servername = servername

def test_full_transfer(tmp_path, monkeypatch):
    # On utilise tmp_path de pytest pour créer un dossier temporaire propre à ce test
    root_dir = tmp_path / "server_root"
    root_dir.mkdir()
    
    # Création d'un fichier de test bidon côté serveur
    test_file = root_dir / "test.txt"
    original_content = b"UCLouvain SRTP Test Data " * 200
    test_file.write_bytes(original_content)
    
    server_port = 8081
    
    # Simulation du lancement du serveur avec nos faux arguments
    monkeypatch.setattr("argparse.ArgumentParser.parse_args", 
                        lambda self: MockArgs("::1", server_port, str(root_dir)))
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # On donne une demi-seconde au serveur pour lier son socket au port
    time.sleep(0.5)
    
    # Simulation du lancement du client
    save_path = tmp_path / "downloaded.model"
    monkeypatch.setattr("argparse.ArgumentParser.parse_args", 
                        lambda self: MockArgs("::1", server_port, str(root_dir), 
                                              save=str(save_path), 
                                              servername=f"http://[::1]:{server_port}/test.txt"))
    
    run_client()
    
    # On s'assure que le fichier est bien arrivé et qu'il est identique à l'octet près
    assert save_path.exists(), "Le fichier n'a pas été sauvegardé par le client"
    assert save_path.read_bytes() == original_content, "Le contenu du fichier reçu est corrompu"


def test_packet_loss_recovery(tmp_path, monkeypatch):
    # Test de robustesse : on vérifie que le Selective Repeat répare bien 20% de pertes réseau
    root_dir = tmp_path / "server_root"
    root_dir.mkdir(exist_ok=True)
    
    test_file = root_dir / "loss_test.txt"
    original_content = b"TEST SRTP AVEC PERTES " * 500 
    test_file.write_bytes(original_content)
    
    # On change de port pour ne pas interférer avec le thread du test précédent
    server_port = 8082 

    # On sauvegarde la vraie fonction d'envoi UDP de Python
    original_sendto = socket.socket.sendto
    
    # On crée une fausse fonction qui a 20% de chance de faire disparaître le paquet
    def lossy_sendto(self, data, address):
        if random.random() < 0.20:
            # Le paquet est jeté, mais on fait croire au code qu'il est bien parti
            return len(data) 
        return original_sendto(self, data, address)
    
    # On remplace temporairement le sendto global par notre version buggée
    monkeypatch.setattr("socket.socket.sendto", lossy_sendto)

    # Démarrage du serveur
    monkeypatch.setattr("argparse.ArgumentParser.parse_args", 
                        lambda self: MockArgs("::1", server_port, str(root_dir)))
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    time.sleep(0.5)
    
    # Démarrage du client
    save_path = tmp_path / "loss_downloaded.model"
    monkeypatch.setattr("argparse.ArgumentParser.parse_args", 
                        lambda self: MockArgs("::1", server_port, str(root_dir), 
                                              save=str(save_path), 
                                              servername=f"http://[::1]:{server_port}/loss_test.txt"))
    
    # Le transfert va faire pas mal de timeouts et de retransmissions, mais doit terminer
    run_client()
    
    # Si le code arrive ici sans timeout fatal, on vérifie l'intégrité
    assert save_path.exists(), "Le transfert s'est bloqué ou a crashé à cause des pertes"
    assert save_path.read_bytes() == original_content, "Le fichier reconstitué est incomplet"