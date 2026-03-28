import socket
import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from packet import encode_packet, decode_packet, PTYPE_DATA, PTYPE_ACK, PTYPE_SACK

RECV_WINDOW = 32 # taille maximale de la fenêtre de réception (en paquets)
TIMEOUT = 4.0 # délai avant de renvoyer un ACK ou d'abandonner (secondes)
UDP_BUFSIZE = 2048 # taille maximale d'un datagramme UDP à lire


def parse_url(url):
    # enlève "http://"
    url = url[len("http://"):]

    # si IPv6 : l'adresse est entre crochets
    if url.startswith('['):
        end = url.index(']')
        host = url[1:end]
        rest = url[end + 2:] # saute ']:'
    else:
        colon = url.index(':')
        host = url[:colon]
        rest = url[colon + 1:]

    slash = rest.index('/')
    port = int(rest[:slash])
    path = rest[slash:]

    return host, port, path


def seq_to_abs(seq, expected):
    # transforme un numéro modulo 2048 en numéro "absolu"
    diff = (seq - (expected % 2048)) % 2048
    return expected + diff


def receive_file(sock, server_addr):
    # buffer pour stocker les paquets reçus en avance
    buffer = {}
    expected = 0
    data = []
    last_ts = 0

    sock.settimeout(TIMEOUT)

    while True:
        try:
            raw, any = sock.recvfrom(UDP_BUFSIZE)
        except socket.timeout:
            # si plus rien n'arrive, on renvoie le dernier ACK
            free = RECV_WINDOW - len(buffer)
            ack = encode_packet(PTYPE_ACK, max(0, free), expected % 2048, b'',last_ts)
            sock.sendto(ack, server_addr)
            continue

        pkt = decode_packet(raw)
        if not pkt or pkt['type'] != PTYPE_DATA:
            continue

        seq = pkt['seqnum']
        last_ts = pkt['timestamp']

        # paquet vide = fin du transfert
        if pkt['length'] == 0 and seq == expected % 2048:
            free = RECV_WINDOW - len(buffer)
            ack = encode_packet(PTYPE_ACK, max(0, free), (expected + 1) % 2048, b'', last_ts)
            sock.sendto(ack, server_addr)
            break

        # on ignore les paquets trop loin devant
        diff = (seq - expected % 2048) % 2048
        if diff >= RECV_WINDOW:
            continue

        abs_seq = seq_to_abs(seq, expected)

        # on stocke le paquet si on ne l'a pas déjà
        if abs_seq >= expected and abs_seq not in buffer:
            buffer[abs_seq] = pkt['payload']

        # on remet dans l'ordre tout ce qu'on peut
        while expected in buffer:
            data.append(buffer.pop(expected))
            expected += 1

        free = RECV_WINDOW - len(buffer)
        ack = encode_packet(PTYPE_ACK, max(0, free), expected % 2048, b'', last_ts)
        sock.sendto(ack, server_addr)

    return b''.join(data)


def main():
    parser = argparse.ArgumentParser(description="Client SRTP")
    parser.add_argument("url", help="http://hostname:port/chemin/vers/fichier")
    parser.add_argument("--save", default="llm.model", help="fichier où sauvegarder le résultat")
    args = parser.parse_args()

    host, port, path = parse_url(args.url)

    infos = socket.getaddrinfo(host, port, socket.AF_INET6, socket.SOCK_DGRAM)
    if not infos:
        sys.exit(1)

    server_addr = infos[0][4]
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)

    # construit le GET
    request = f"GET {path}\r\n".encode("ascii")
    ts = int(time.monotonic() * 1000) & 0xFFFFFFFF
    get_pkt = encode_packet(PTYPE_DATA, RECV_WINDOW, 0, request, ts)

    sock.settimeout(TIMEOUT)

    # jusqu'à 10 tentatives pour envoyer le GET et recevoir l'ACK initial
    ok = False
    for steps in range(10):
        sock.sendto(get_pkt, server_addr)

        try:
            raw, any = sock.recvfrom(UDP_BUFSIZE)
            ack = decode_packet(raw)

            if ack and ack['type'] in (PTYPE_ACK, PTYPE_SACK) and ack['seqnum'] == 1:
                ok = True
                break

        except socket.timeout:
            continue

    if not ok:
        sys.exit(1)

    data = receive_file(sock, server_addr)

    save_dir = os.path.dirname(os.path.abspath(args.save))
    os.makedirs(save_dir, exist_ok=True)

    with open(args.save, "wb") as f:
        f.write(data)


if __name__ == "__main__":
    main()