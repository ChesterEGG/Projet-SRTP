import socket
import sys
import argparse
from urllib.parse import urlparse
from packet import Packet

def client():
    #récupération des arguments passé en ligne de commande
    parser = argparse.ArgumentParser()
    parser.add_argument("servername", help="http://hostname:port/path")
    parser.add_argument("--save", default="llm.model", help="Save location")
    args = parser.parse_args()

    #récupération des données de l'url
    url = urlparse(args.servername)
    hostname = url.hostname
    port = url.port
    path = url.path

    #création du socket
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    
    #la requête HTTP 0.9
    request = f"GET {path}".encode('ascii')

    # 63 car 6bit
    window_size = 63

    first_packet = Packet(1, window_size, 0, len(request), 0, request)
    sock.sendto(first_packet.encode(), (hostname, port))
    
    # Variable pour savoir si le serveur a répondu au GET
    connected = False 

    expected_seq = 0
    content = b""
    stockage_paquets = {} # dictionnaire pour stocker les paquets reçus dans le désordre

    while True:
        try:
            # Timeout court si pas encore connecté, long si on télécharge
            if connected:
                sock.settimeout(2.0)
            else:
                sock.settimeout(0.5)
            data, addr = sock.recvfrom(1040) #car on nous demande 1024 de payload + 16 d'entête
            packet = Packet.decode(data)

            #si décodage échoue ou si c'est pas un paquet de type data, alors on l'ignore
            if not packet or packet.p_type != 1:
                continue
            
            connected = True

            
            if packet.length == 0: 
                # On confirme le paquet de fin en acquittant son seqnum + 1
                ack_fin = Packet(2, window_size, (packet.seqnum + 1) % 2048, 0, packet.timestamp)
                sock.sendto(ack_fin.encode(), addr)
                break
            
            seq = packet.seqnum
            dist = (seq - expected_seq) % 2048
            
            #selective repeat : On stocke si c'est dans la fenêtre
            if dist < window_size and seq not in stockage_paquets:
                stockage_paquets[seq] = packet.payload
                
            #On réassemble tout ce qui est en séquence
            while expected_seq in stockage_paquets:
                content += stockage_paquets.pop(expected_seq)
                expected_seq = (expected_seq + 1) % 2048
                
            # Calcul de la place restante dans le buffer
            current_window = window_size - len(stockage_paquets)
            if current_window < 0: 
                current_window = 0
            
            ack = Packet(2, current_window, expected_seq, 0, packet.timestamp)
            sock.sendto(ack.encode(), addr)
        # si le temps d'attente est dépassé on renvoie le GET si le serveur n'a jamais répondu.
        except socket.timeout:
            if not connected:
                sock.sendto(first_packet.encode(), (hostname, port))
            else:
                break

    if content:
        with open(args.save, "wb") as f: 
            f.write(content)

if __name__ == "__main__":
    client()
