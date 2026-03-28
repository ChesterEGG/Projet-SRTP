import socket
import sys
import argparse
from urllib.parse import urlparse
from encode_decode import Packet, PTYPE_DATA, PTYPE_ACK

MAX_WINDOW = 63 # max 6 bits donc [0,63] 

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('--save', default='llm.model')
    args = parser.parse_args()

    parsed   = urlparse(args.url)
    hostname = parsed.hostname
    port     = parsed.port
    path     = parsed.path

    # le client envoie sa requête sous la forme GET /chemin/vers/le/fichier encodée en ASCII.
    request = f"GET {path}".encode('ascii') 

    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as s:
            s.connect((hostname, port))

            # on met à 2 secondes car le server devrait répondre vite sinon ça veut dire que la requête a été perdue 
            # et on doit renvoyer la requête donc
            s.settimeout(2.0)
            first_paquet = None

            for i in range(5):
                s.send(request)
                print(f"Requête envoyée : GET {path} (tentative {i+1})", file=sys.stderr)
                try:
                    first_paquet, _ = s.recvfrom(65535)
                    break  # on a reçu une réponse du serveur
                except socket.timeout:
                    print("Pas de réponse, on réessaie...", file=sys.stderr)
                    pass

            if first_paquet is None:
                print("Aucune réponse du serveur après plusieurs tentatives.", file=sys.stderr)
                sys.exit(1)

            # on met un timeout plus long car le server retransmet après 1.5 seconde de timeout
            # + 2 secondes max de temps de trajet dans le réseaux donc on met 4 secondes pour ếtre sur 
            s.settimeout(4.0)
            buffer_reception = {} # ça stocke les paquets reçus hors-ordre
            expected_seqnum = 0
            received_pieces = []
            fin_transfert = False 
            current_paquet = first_paquet

            while True:
                packet = Packet.decode(current_paquet)

                if packet is None:
                    print("Paquet invalide reçu, ignoré", file=sys.stderr)
                    pass
                else:
                    if packet.ptype != PTYPE_DATA:
                        print(f"Paquet ignoré (type={packet.ptype})", file=sys.stderr)
                        pass

                    else:
                        # si un paquet DATA a .length==0 et que le numéro de séquence correspond au dernier
                        # numéro d’acquittement envoyé par le destinataire, ça signifie que le transfert est terminé
                        if packet.length == 0 and packet.seqnum == expected_seqnum:
                            print("Fin de transfert reçue", file=sys.stderr)
                            fin_transfert = True
                            break

                        # c'est la différence entre le seqnum qu'on reçoit et celui attendu et si il se trouve 
                        # dans les bornes de la fenêtre on le met dans le buffer pour ne pas le perdre ensuite quand on
                        # arrivera à ce seqnum évitant donc de la retransmission inutile 
                        distance = (packet.seqnum - expected_seqnum) % 2048

                        if distance < MAX_WINDOW:
                            if packet.seqnum not in buffer_reception:
                                buffer_reception[packet.seqnum] = packet.payload
                        else:
                            print(f"Paquet {packet.seqnum} ignoré (hors fenêtre)", file=sys.stderr)
                            pass

                        # on vide tout ce qui est consécutif dans le buffer dès qu'un paquet manquant est arrivé 
                        while expected_seqnum in buffer_reception:
                            # On ajoute le morceau à la liste (très rapide)
                            received_pieces.append(buffer_reception.pop(expected_seqnum))
                            expected_seqnum = (expected_seqnum + 1) % 2048

                        # on envoie l'ack au server 
                        places_vides = MAX_WINDOW - len(buffer_reception)
                        ack = Packet(
                            PTYPE_ACK,
                            window=places_vides,
                            length=0,
                            seqnum=expected_seqnum,
                            timestamp=packet.timestamp
                        )
                        s.send(ack.encode())

                # on lit le prochain paquet 
                try:
                    current_paquet, _ = s.recvfrom(65535)
                except socket.timeout:
                    if fin_transfert:
                        print("Timeout après fin de transfert, on termine.", file=sys.stderr)
                        pass
                    else:
                        print("Timeout : plus de données reçues, on termine.", file=sys.stderr)
                        pass
                    break

            # on écrit toutes les données reçues dans un fichier. 
            # On fusionne tous les morceaux en un seul objet bytes
            received_data = b''.join(received_pieces)

            with open(args.save, 'wb') as f:
                f.write(received_data)  
            print(f"Fichier sauvegardé dans {args.save}", file=sys.stderr)

    except socket.error as e:
        print(f"Erreur socket : {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()