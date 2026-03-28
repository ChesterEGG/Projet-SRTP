import socket
import sys
import os
import argparse
import select
import time

from encode_decode import Packet, PTYPE_DATA, PTYPE_ACK, PTYPE_SACK

def main():
    #lecture des arguments de la ligne de commande
    parser = argparse.ArgumentParser()
    parser.add_argument('hostname')
    parser.add_argument('port', type=int)
    parser.add_argument('--root', default='.')
    args = parser.parse_args()
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s:
            s.bind((args.hostname, args.port))
            print(f"Serveur démarré sur {args.hostname}:{args.port}", file=sys.stderr)

            while True:
                # on reçoit la requête http
                paquet, client_addr = s.recvfrom(65535)
                try:
                    request = paquet.decode('ascii').strip()
                except UnicodeDecodeError:
                    print("Paquet non-ASCII reçu, ignoré", file=sys.stderr)
                    continue
                print(f"Requête reçue : {request} de {client_addr}", file=sys.stderr)
                if not request.startswith('GET '):
                    print("Requête invalide, ignorée", file=sys.stderr)
                    continue
                
                #on convertit la requête pour pouvoir l'utiliser et trouver le fichier demandé
                path = request.split(' ')[1]
                filepath = os.path.join(args.root, path.lstrip('/'))
                if not os.path.exists(filepath):
                    print(f"Fichier {filepath} introuvable", file=sys.stderr)
                    end_packet = Packet(PTYPE_DATA, window=0, length=0, seqnum=0, timestamp=0, payload=b'')
                    s.sendto(end_packet.encode(), client_addr)
                    continue

                # on défini les variables pour la sliding window
                seqnum = 0
                base = 0
                window_size = 1
                buffer_envoi = {}
                file_ended = False

                #on va chercher le fichier et commencer le transfert des paquets
                with open(filepath, 'rb') as f:
                    while not file_ended or len(buffer_envoi) > 0:
                        #mécanisme anti-blocage (sur le modèle du mécanisme "Zero Window Probe" de TCP)
                        if len(buffer_envoi) == 0:
                            effective_window = max(window_size, 1)
                        else:
                            effective_window = window_size
                        while len(buffer_envoi) < effective_window and not file_ended:
                            #on crée le payload du paquet à envoyer et on le mettra ensuite dans le paquet
                            packet_payload = f.read(1024)
                            if not packet_payload:
                                file_ended = True
                                break
                            ts = int(time.time() * 1000) & 0xFFFFFFFF
                            packet = Packet(PTYPE_DATA, window=0, length=len(packet_payload), seqnum=seqnum, timestamp=ts, payload=packet_payload)
                            s.sendto(packet.encode(), client_addr)
                            #à chaque paquet envoyé on met à jour le buffer d'envoi qui nous servira plus tard pour les retransmission de paquet
                            buffer_envoi[seqnum] = {'packet': packet, 'time': time.time()}
                            print(f"Paquet envoyé : seqnum={seqnum}", file=sys.stderr)
                            seqnum = (seqnum + 1) % 2048

                        #réception et gestion des ack
                        #on utilise select pour savoir quand le socket est prêt à être lu sans devoir bloquer l'exécution du programme
                        ready_to_read, _, _ = select.select([s], [], [], 0.05)
                        if ready_to_read:
                            paquet_ack, _ = s.recvfrom(65535)
                            ack = Packet.decode(paquet_ack)
                            if ack is not None and ack.ptype in (PTYPE_ACK, PTYPE_SACK):
                                window_size = ack.window
                                rtt = (int(time.time() * 1000) & 0xFFFFFFFF) - ack.timestamp
                                print(f"ACK reçu : attend seqnum={ack.seqnum}, fenêtre={window_size}, RTT={rtt}ms", file=sys.stderr)

                                #on met à jour le buffer d'envoi en fonction des acks qu'on reçoit
                                while base != ack.seqnum and len(buffer_envoi) > 0:
                                    if base in buffer_envoi:
                                        del buffer_envoi[base]
                                    base = (base + 1) % 2048

                        #gestion des retransmissions (quand on n'a pas reçu de ack avant la fin du timeout)
                        TIMEOUT = 1.5
                        current_time = time.time()
                        for seq in list(buffer_envoi.keys()):
                            if current_time - buffer_envoi[seq]['time'] > TIMEOUT:
                                print(f"Timeout ! Renvoi seqnum={seq}", file=sys.stderr)
                                s.sendto(buffer_envoi[seq]['packet'].encode(), client_addr)
                                buffer_envoi[seq]['time'] = current_time

                #quand on a envoyé tout le fichier, on envoie le paquet de fin de transfert (avec length=0)
                end_packet = Packet(PTYPE_DATA, window=0, length=0, seqnum=seqnum, timestamp=0, payload=b'')
                s.sendto(end_packet.encode(), client_addr)
                print("Fin de transfert envoyée", file=sys.stderr)

    except socket.error as e:
        print(f"Erreur socket : {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()