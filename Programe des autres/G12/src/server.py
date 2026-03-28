import socket
import sys
import os
import time
import threading
import queue
import argparse
from packet import Packet

client_queues = {} 

def handle_client(addr, sock, root_dir, first_packet):
    queue_client = client_queues[addr]
    request = first_packet.payload.decode('ascii', errors='ignore') #lit la requête http et si ca n'est pas un get on stop
    if not request.startswith("GET "):
        return
    
    file_path = request.split(" ")[1].lstrip("/")
    full_path = os.path.join(root_dir, file_path)
    
    if not (os.path.exists(full_path) and os.path.isfile(full_path)):
        nul_packet = Packet(1, 1, 0, 0, first_packet.timestamp)
        sock.sendto(nul_packet.encode(), addr)   #si le fichier est pas sur notre disque, on envoie un packet vide pour stopper le client
        return

    
    # Lecture complète du fichier en mémoire pour pouvoir retransmettre avec Selective Repeat
    blocks = []
    with open(full_path, "rb") as f:
        while True:
            block = f.read(1024)
            if not block: break
            blocks.append(block)
            
    # On ajoute un bloc vide à la fin pour signaler la fin du fichier proprement
    blocks.append(b"")

    base = 0
    next_seq = 0
    window_size = 1 # Fenêtre fixée à 1 initialement selon l'énoncé
    acked = [False] * len(blocks)
    timers = {}
    
    while base < len(blocks):
        #Envoi des paquets dans la limite de la fenêtre permise par le client
        while next_seq < base + window_size and next_seq < len(blocks):
            if not acked[next_seq]:
                #Temps en millisecondes pour le timestamp
                temps_actuel = int(time.time() * 1000)
                #On force la valeur à rester sous la limite des 32 bits (2^32) pour éviter un bug
                timestamp = temps_actuel % 4294967296
                packet = Packet(1, window_size, next_seq % 2048, len(blocks[next_seq]), timestamp, blocks[next_seq])                
                sock.sendto(packet.encode(), addr)
                timers[next_seq] = time.time()
            next_seq += 1
            
        # Serveur lit les ACKs envoyés par le client
        try:
            ack_packet = queue_client.get(timeout=0.1)
            window_size = ack_packet.window
            ack_num = ack_packet.seqnum
            
            # On calcule combien de paquets ce ACK valide d'un coup
            dist = (ack_num - (base % 2048)) % 2048
            
            # Mise à jour de notre liste de suivi
            if dist > 0 and dist <= (next_seq - base):
                for i in range(base, base + dist):
                    acked[i] = True
                base += dist
                
        except queue.Empty:
            pass
            
        #Retransmission des paquets perdus (ceux qui ont dépassé le timer de 0.5s)
        now = time.time()
        for i in range(base, next_seq):
            if not acked[i] and (now - timers.get(i, 0) > 0.5):
                temps_actuel = int(time.time() * 1000)
                timestamp = temps_actuel % 4294967296
                packet = Packet(1, window_size, i % 2048, len(blocks[i]), timestamp, blocks[i])
                sock.sendto(packet.encode(), addr)
                timers[i] = now

def server():
    #récupération des arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("hostname", help="IPv6 address")
    parser.add_argument("port", type=int, help="UDP port")
    parser.add_argument("--root", default=".", help="Root directory")
    args = parser.parse_args()

    #création du socket
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((args.hostname, args.port))
    sock.settimeout(2.0)

    while True:
        try:
            data, addr = sock.recvfrom(1040) #car on nous demande 1024 de payload + 16 d'entête
            packet = Packet.decode(data)
            #si décodage échoue, on ignore le packet
            if not packet:
                continue

            #requete GET(type 1) de client, si on ne connait pas encore le client on lui crée une queue et on l'attribue a un thread.
            if packet.p_type == 1: 
                if addr not in client_queues:
                    client_queues[addr] = queue.Queue()
                    thread_client =threading.Thread(target=handle_client, args=(addr, sock, args.root, packet), daemon=True)
                    thread_client.start()
            elif packet.p_type == 2 or packet.p_type == 3:    
                if addr in client_queues:#client qui envoie un ACK (on le place dans sa queue)
                    client_queues[addr].put(packet)

        #si personne ne parle au serveur on boucle 
        except (socket.timeout):
            continue
        #cas de controle C 
        except KeyboardInterrupt:
            break

if __name__ == "__main__":
    server()
