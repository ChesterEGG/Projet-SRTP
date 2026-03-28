import socket
import sys
import os
import time
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from packet import encode_packet, decode_packet, PTYPE_DATA, PTYPE_ACK, PTYPE_SACK

RETRANSMIT_TIMEOUT = 3.0 # délai avant retransmission d'un paquet non acquitté (secondes)
UDP_BUFSIZE = 2048 # taille maximale d'un datagramme UDP à lire


def seq_to_abs(seq, base):
    # transforme un numéro modulo 2048 en numéro absolu
    diff = (seq - base % 2048) % 2048
    return base + diff


def send_file(sock, addr, chunks, initial_window, get_timestamp=0):
    # nombre total de morceaux à envoyer
    n = len(chunks)

    send_base = 0 # plus vieux paquet non encore acquitté
    next_seq = 0 # prochain paquet à envoyer
    window = max(1, initial_window) # taille de fenêtre annoncée par le client
    in_flight = {} # abs_seq -> (payload, timestamp, heure d'envoi)

    sock.settimeout(0.05)

    while True:
        # on remplit la fenêtre tant qu'on peut
        while window > 0 and next_seq - send_base < window and next_seq < n:
            seq = next_seq % 2048
            payload = chunks[next_seq]
            ts = int(time.monotonic() * 1000) & 0xFFFFFFFF

            pkt = encode_packet(PTYPE_DATA, 0, seq, payload, ts)
            sock.sendto(pkt, addr)

            in_flight[next_seq] = (payload, ts, time.monotonic())
            next_seq += 1

        if send_base >= n:
            break

        try:
            raw, src = sock.recvfrom(UDP_BUFSIZE)

            if src != addr:
                continue

            ack = decode_packet(raw)
            if not ack:
                continue

            # si le client renvoie le GET
            if ack["type"] == PTYPE_DATA and ack["seqnum"] == 0:
                reply = encode_packet(PTYPE_ACK, 0, 1, b"", get_timestamp)
                sock.sendto(reply, src)
                continue

            if ack["type"] not in (PTYPE_ACK, PTYPE_SACK):
                continue

            window = ack["window"]
            ack_abs = min(seq_to_abs(ack["seqnum"], send_base), n)

            if ack_abs > send_base:
                for i in range(send_base, ack_abs):
                    in_flight.pop(i, None)
                send_base = ack_abs

        except socket.timeout:
            pass

        # retransmet les paquets dont le timer a expiré
        now = time.monotonic()
        for abs_seq in sorted(in_flight):
            payload, ts, send_time = in_flight[abs_seq]

            if now - send_time > RETRANSMIT_TIMEOUT:
                seq = abs_seq % 2048
                new_ts = int(now * 1000) & 0xFFFFFFFF

                pkt = encode_packet(PTYPE_DATA, 0, seq, payload, new_ts)
                sock.sendto(pkt, addr)

                in_flight[abs_seq] = (payload, new_ts, now)

    # paquet vide pour dire que le transfert est fini
    end_seq = n % 2048
    ts = int(time.monotonic() * 1000) & 0xFFFFFFFF
    end_pkt = encode_packet(PTYPE_DATA, 0, end_seq, b"", ts)

    # on répète jusqu'à recevoir l'ACK final (max 30 tentatives)
    for steps in range(30):
        sock.sendto(end_pkt, addr)

        try:
            raw, src = sock.recvfrom(UDP_BUFSIZE)

            if src != addr:
                continue

            ack = decode_packet(raw)
            if ack and ack["type"] in (PTYPE_ACK, PTYPE_SACK):
                if ack["seqnum"] == (n + 1) % 2048:
                    return

        except socket.timeout:
            pass


def handle_request(sock, data, addr, root):
    # traite une requête GET du client
    pkt = decode_packet(data)
    if not pkt or pkt["type"] != PTYPE_DATA or pkt["seqnum"] != 0:
        return

    try:
        request = pkt["payload"].decode("ascii").strip()
    except Exception:
        return

    if not request.startswith("GET "):
        return

    path = request.split()[1].lstrip("/")
    filepath = os.path.normpath(os.path.join(root, path))
    abs_root = os.path.abspath(root)

    # évite qu'un client sorte du dossier root
    if not (os.path.abspath(filepath) + os.sep).startswith(abs_root + os.sep):
        return

    # on acquitte le GET
    ack = encode_packet(PTYPE_ACK, 0, 1, b"", pkt["timestamp"])
    sock.sendto(ack, addr)

    try:
        with open(filepath, "rb") as f:
            file_data = f.read()
    except FileNotFoundError:
        file_data = b""

    if file_data:
        chunks = []
        for i in range(0, len(file_data), 1024):
            chunk = file_data[i:i + 1024]
            chunks.append(chunk)
    else:
        chunks = []

    send_file(sock, addr, chunks, pkt["window"], get_timestamp=pkt["timestamp"])


def main():
    parser = argparse.ArgumentParser(description="Serveur SRTP")
    parser.add_argument("hostname")
    parser.add_argument("port", type=int)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
    except AttributeError:
        pass

    sock.bind((args.hostname, args.port, 0, 0))

    while True:
        sock.settimeout(5.0)

        try:
            data, addr = sock.recvfrom(UDP_BUFSIZE)
        except socket.timeout:
            continue

        handle_request(sock, data, addr, args.root)


if __name__ == "__main__":
    main()