import argparse
import os.path
import socket
import sys

from packet import Packet

def send_file(sock, client_address, filepath, window):
    """
    Transforme un fichier en packet et l'envoi
    """
    if not os.path.exists(filepath):
        print("Fichier non trouver", file=sys.stderr)
        packet = Packet(1, window, 0, 0, payload=b'')
        sock.sendto(packet.pack(), client_address)
        return

    print("Envoie du fichier", file=sys.stderr)

    with open(filepath, 'rb') as f:
        seqnum = 0
        while True:
            chunk = f.read(1024)

            if not chunk:
                packet = Packet(1, window, seqnum, 0, payload=b'')
                sock.sendto(packet.pack(), client_address)
                break

            packet = Packet(1, window, seqnum, 0, payload=chunk)
            sock.sendto(packet.pack(), client_address)
            seqnum = (seqnum + 1) %2048


def start_server():
    """
    Démarrage du server
    """

    # Configuration des arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("hostname")
    parser.add_argument("port", type=int)
    parser.add_argument("--root", default=".")

    args = parser.parse_args()

    print(f"Démarrage du server sur [{args.hostname}]: {args.port}", file=sys.stderr)
    print(f"Racine des fichiers : {os.path.abspath(args.root)}", file=sys.stderr)

    # Création du socket
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        sock.bind((args.hostname, args.port))
    except socket.error as e:
        print(f"Erreur : {e}",file=sys.stderr)

    # Reception des packet
    while True:
        data, address = sock.recvfrom(1024)
        packet = Packet.unpack(data)

        # Packet de type DATA
        if packet.type == 1:
            payload = packet.payload.decode('ascii').strip()

            if (payload[0:4] == "GET "):
                filepath = payload[4:].strip()
                path = os.path.join(args.root, filepath.lstrip("/"))

                print(f"Client {address} demande : {path}", file=sys.stderr)
                send_file(sock, address, path, 32)

if __name__ == "__main__":
    start_server()