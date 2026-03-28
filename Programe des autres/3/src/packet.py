import struct
import zlib

PTYPE_DATA = 1
PTYPE_ACK = 2
PTYPE_SACK = 3

MAX_PAYLOAD = 1024
MAX_SEQNUM = 2048 # 2^11


def encode_packet(ptype, window, seqnum, payload=b"", timestamp=0):
    # structure de l'entête (32 bits) :
    # -> bits 31-30 : type (2 bits)
    # -> bits 29-24 : window (6 bits)
    # -> bits 23-11 : length (13 bits)
    # -> bits 10-0 : seqnum (11 bits)

    # vérifie les valeurs
    if ptype not in (PTYPE_DATA, PTYPE_ACK, PTYPE_SACK):
        raise ValueError("Type invalide")

    if window < 0 or window > 63:
        raise ValueError("Window invalide")

    if seqnum < 0 or seqnum >= MAX_SEQNUM:
        raise ValueError("Seqnum invalide")

    length = len(payload)

    if length > MAX_PAYLOAD:
        raise ValueError("Payload trop grand")

    # construit l'entête (32 bits)
    header_int = (ptype << 30) | (window << 24) | (length << 11) | seqnum
    header = struct.pack("!I", header_int)

    # timestamp sur 4 octets
    ts_bytes = struct.pack("!I", timestamp & 0xFFFFFFFF)

    # CRC1 = protection de l'entête
    crc1 = zlib.crc32(header + ts_bytes) & 0xFFFFFFFF
    crc1_bytes = struct.pack("!I", crc1)

    packet = header + ts_bytes + crc1_bytes

    # si on a un payload on ajoute CRC2
    if payload:
        crc2 = zlib.crc32(payload) & 0xFFFFFFFF
        crc2_bytes = struct.pack("!I", crc2)
        packet = packet + payload + crc2_bytes

    return packet


def decode_packet(data):
    # paquet trop court
    if len(data) < 12:
        return None

    header = data[0:4]
    ts_bytes = data[4:8]
    crc1_received = struct.unpack("!I", data[8:12])[0]

    # vérifie le CRC1
    crc1_calc = zlib.crc32(header + ts_bytes) & 0xFFFFFFFF
    if crc1_calc != crc1_received:
        return None

    header_int = struct.unpack("!I", header)[0]

    ptype  = (header_int >> 30) & 0x3 # 2 bits
    window = (header_int >> 24) & 0x3F # 6 bits
    length = (header_int >> 11) & 0x1FFF # 13 bits
    seqnum = header_int & 0x7FF # 11 bits

    if ptype not in (PTYPE_DATA, PTYPE_ACK, PTYPE_SACK):
        return None

    if length > MAX_PAYLOAD:
        return None

    timestamp = struct.unpack("!I", ts_bytes)[0]

    payload = b""

    if length > 0:
        rest = data[12:]

        if len(rest) < length + 4:
            return None

        payload = rest[:length]
        crc2_received = struct.unpack("!I", rest[length:length + 4])[0]

        crc2_calc = zlib.crc32(payload) & 0xFFFFFFFF
        if crc2_calc != crc2_received:
            return None

    return {
        "type": ptype,
        "window": window,
        "seqnum": seqnum,
        "length": length,
        "timestamp": timestamp,
        "payload": payload,
    }