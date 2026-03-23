import argparse
import os.path
import socket
import sys
import time

from packet import Packet

def send_file(sock, client_address, filepath, window):
    """
    Transforme un fichier en packet et l'envoi
    """
    if not os.path.exists(filepath):
        print("Fichier non trouver", file=sys.stderr)
        # Envoie d'un packet vide
        packet = Packet(1, window, 0, int(time.time()), payload=b'')
        sock.sendto(packet.pack(), client_address)
        return

    print("Envoie du fichier", file=sys.stderr)

    packets = []
    seqnum = 0
    try:
        with open(filepath, 'rb') as f:

            # Découpage du contenu du fichier en packet de taille 1024 max
            while True:
                chunk = f.read(1024)
                packets.append(Packet(1, window, seqnum, int(time.time()), chunk))

                if not chunk:
                    packet = Packet(1, window, seqnum, int(time.time()), payload=b'')
                    sock.sendto(packet.pack(), client_address)
                    break

                seqnum = (seqnum + 1) % 2048
    except Exception as e:
        print(f"Erreur de lecture de fichier: {e}", file=sys.stderr)
        return


    last_ack = -1
    last_sent = -1
    timestamp = {}


    # On attend 100ms max pour un ACK
    sock.settimeout(0.1)

    try:
        while last_ack < len(packets) -1:
            # Envoie tant que la fenêtre le permet
            while last_sent - last_ack < window and last_sent < len(packets) - 1:
                last_sent += 1
                packet = packets[last_sent]
                sock.sendto(packet.pack(), client_address)
                timestamp[packet.seqnum] = time.time()
                print(f"Envoie du segment {packet.seqnum} (Index {last_sent})", file=sys.stderr)


            # Reception des ACK
            try:
                data, address = sock.recvfrom(2048)
                ack_packet = Packet.unpack(data)

                if ack_packet.type == 2: # ACK
                    """
                    ack_seqnum = ack_packet.seqnum
                    next_expected = last_ack + 1
                    if packets[next_expected].seqnum == ack_seqnum:
                        last_ack = next_expected - 1
                        print(f"ACK recu pour la séquence {ack_seqnum}", file=sys.stderr)
                    elif (ack_seqnum > packets[next_expected].seqnum):
                        last_ack = next_expected
                    """
                    target_idx = ack_packet.seqnum - 1

                    if target_idx > last_ack:
                        last_ack = target_idx
                        print(f"ACK recu : fenetre avance a l'idx {last_ack}", file=sys.stderr)

            except socket.timeout:
                pass

            except ConnectionResetError:
                # Gestion du bug Windows 10054
                print("Note : Le client a fermé la connexion prématurément (probablement fini).", file=sys.stderr)
                break

            # Retransmission du message due au timeout
            now = time.time()
            for i in range(last_ack + 1, last_sent + 1):
                if i in timestamp and (now - timestamp[i] > 0.5):
                    print(f"Timeout, retransmission du seq {packets[i].seqnum}", file=sys.stderr)
                    sock.sendto(packets[i].pack(), client_address)
                    timestamp[i] = now
    except Exception as e:
        print(f"Erreur (Envoie): {e}", file=sys.stderr)
    finally:
        sock.settimeout(None)
        print("Transfert terminé", file=sys.stderr)




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
        print(f"Erreur de socket : {e}",file=sys.stderr)
        sys.exit(1)

    # Reception des packet
    while True:
        try:
            sock.settimeout(None)
            data, address = sock.recvfrom(2048)
            packet = Packet.unpack(data)

            # Packet de type DATA
            if packet.type == 1:
                try:
                    payload = packet.payload.decode('ascii').strip()

                    if (payload[0:4] == "GET "):
                        filepath = payload[4:].strip()
                        path = os.path.join(args.root, filepath.lstrip("/"))

                        print(f"Client {address} demande : {path}", file=sys.stderr)
                        send_file(sock, address, path, 32)
                except Exception as e:
                    print(f"Erreur (Lecture de la requête) : {e}", file=sys.stderr)

        except KeyboardInterrupt:
            print("Arret du server", file=sys.stderr)
            break
        except Exception as e:
            print(f"Erreur (Boucle principale): {e}", file=sys.stderr)
    sock.close()

if __name__ == "__main__":
    start_server()