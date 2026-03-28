import argparse
import socket
import sys
import time
from urllib.parse import urlparse

from packet import Packet


def start_client():
    """
    Démarrage du client
    """

    # Configuration des arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("servername")
    parser.add_argument("--save", default="llm.model")
    args = parser.parse_args()

    # Parser l'URL
    try:
        parsed_url = urlparse(args.servername)
        if parsed_url.scheme != "http":
            raise ValueError("L'URL ne commence pas par http://")

        hostname = parsed_url.hostname
        port = parsed_url.port
        path = parsed_url.path

        if not hostname or not port or not path:
            raise ValueError("Mauvais URL (hostname, port, path)")

    except:
        print(f"Erreur d'url", file=sys.stderr)
        sys.exit(1)

    # Création du socket
    try:
        sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    except socket.error as e:
        print(f"Erreur d'init du socket: {e}", file=sys.stderr)
        sys.exit(1)

    # Création du packet de requête
    request = f"GET {path}".encode("ascii")
    packet = Packet(1, 32, 0, 0, request)

    server_adress = (hostname, port)
    sock.sendto(packet.pack(), server_adress)
    print("Requête envoyer", file=sys.stderr)

    expected_seqnum = 0
    buffer = {}

    # Ouvrir le fichier de réception
    with open(args.save, "wb") as f:
        print(f"Reception des données dans {args.save}", file=sys.stderr)

        # Reception des données et transfert dans le fichier
        while True:
            data, address = sock.recvfrom(2048)
            packet = Packet.unpack(data)

            if packet.type == 1: # DATA
                seqnum = packet.seqnum

                # Si c'est un nouveau packet on le met dans le buffer
                if seqnum not in buffer and seqnum >= expected_seqnum:
                    buffer[seqnum] = packet.payload

                # On ecrit tant qu'on a le packet dans le buffer
                while expected_seqnum in buffer:
                    payload = buffer.pop(expected_seqnum)

                    if len(payload) > 0:
                        f.write(payload)
                        print(f"Segment {expected_seqnum} écrit", file=sys.stderr)
                        expected_seqnum = (expected_seqnum + 1) % 2048
                    else:
                        print("Fin du transfert", file=sys.stderr)
                        # Création et envoie du ACK de fin au server
                        ack = Packet(2, 32, (expected_seqnum + 1) % 2048, packet.timestamp)
                        sock.sendto(ack.pack(), address)
                        time.sleep(0.1)
                        return


                # Création et envoie du ACK
                ack = Packet(2, 32, expected_seqnum, packet.timestamp)
                sock.sendto(ack.pack(), address)




if __name__ == "__main__":
    start_client()