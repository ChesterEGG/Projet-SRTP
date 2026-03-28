import os
import sys
import struct
import zlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "codes"))

from packet import encode_packet, decode_packet, PTYPE_DATA, PTYPE_ACK


# tests sur encode_packet

def test_data_packet_size():
    # un paquet DATA avec 5 octets de payload doit faire 12 (entête) + 5 + 4 (CRC2) = 21 octets
    pkt = encode_packet(PTYPE_DATA, 10, 5, b"hello", 0)
    assert len(pkt) == 21


def test_ack_packet_size():
    # un ACK sans payload doit faire exactement 12 octets (entête + timestamp + CRC1)
    pkt = encode_packet(PTYPE_ACK, 0, 42, b"", 0)
    assert len(pkt) == 12


def test_invalid_type():
    # un type de paquet inexistant doit lever une ValueError
    with pytest.raises(ValueError):
        encode_packet(0, 0, 0, b"")


def test_window_too_big():
    # la fenêtre est codée sur 6 bits donc 64 dépasse le max autorisé (63)
    with pytest.raises(ValueError):
        encode_packet(PTYPE_DATA, 64, 0, b"")


def test_seqnum_too_big():
    # le seqnum est codé sur 11 bits donc 2048 dépasse le max autorisé (2047)
    with pytest.raises(ValueError):
        encode_packet(PTYPE_DATA, 0, 2048, b"")


def test_payload_too_big():
    # un payload de 1025 octets dépasse MAX_PAYLOAD (1024)
    with pytest.raises(ValueError):
        encode_packet(PTYPE_DATA, 0, 0, b"x" * 1025)


# tests encode -> decode

def test_data_packet_roundtrip():
    # encode puis décode un paquet DATA et vérifie que tous les champs sont conservés
    payload = b"Hello, SRTP!"
    pkt = encode_packet(PTYPE_DATA, 32, 7, payload, 9999)
    decoded = decode_packet(pkt)

    assert decoded is not None
    assert decoded["type"] == PTYPE_DATA
    assert decoded["window"] == 32
    assert decoded["seqnum"] == 7
    assert decoded["length"] == len(payload)
    assert decoded["payload"] == payload
    assert decoded["timestamp"] == 9999


def test_ack_roundtrip():
    # encode puis décode un ACK et vérifie le type, le seqnum et l'absence de payload
    pkt = encode_packet(PTYPE_ACK, 0, 100, b"", 42)
    decoded = decode_packet(pkt)

    assert decoded is not None
    assert decoded["type"] == PTYPE_ACK
    assert decoded["seqnum"] == 100
    assert decoded["payload"] == b""


def test_empty_payload_roundtrip():
    # un paquet DATA sans payload doit se décoder correctement
    pkt = encode_packet(PTYPE_DATA, 5, 0, b"", 0)
    decoded = decode_packet(pkt)

    assert decoded is not None
    assert decoded["length"] == 0
    assert decoded["payload"] == b""


def test_max_payload_roundtrip():
    # un payload de 1024 octets (taille maximale) doit passer sans erreur
    payload = bytes(range(256)) * 4
    pkt = encode_packet(PTYPE_DATA, 1, 0, payload, 0)
    decoded = decode_packet(pkt)

    assert decoded is not None
    assert decoded["payload"] == payload


# tests sur les erreurs

def test_packet_too_short():
    # un paquet de moins de 12 octets doit être rejeté
    assert decode_packet(b"\x00" * 11) is None


def test_bad_crc1():
    # un bit corrompu dans le CRC1 doit invalider le paquet
    pkt = bytearray(encode_packet(PTYPE_DATA, 0, 0, b"test", 0))
    pkt[8] ^= 0xFF
    assert decode_packet(bytes(pkt)) is None


def test_bad_crc2():
    # un bit corrompu dans le CRC2 doit invalider le paquet
    pkt = bytearray(encode_packet(PTYPE_DATA, 0, 0, b"test", 0))
    pkt[-1] ^= 0xFF
    assert decode_packet(bytes(pkt)) is None


def test_truncated_payload():
    # un paquet tronqué (payload + CRC2 manquants) doit être rejeté
    pkt = encode_packet(PTYPE_DATA, 0, 0, b"x" * 100, 0)
    assert decode_packet(pkt[:20]) is None


def test_length_over_1024():
    # un paquet avec length=1025 dans l'entête doit être rejeté par decode
    header_int = (PTYPE_DATA << 30) | (0 << 24) | (1025 << 11) | 0
    header = struct.pack("!I", header_int)
    timestamp = struct.pack("!I", 0)
    crc1 = struct.pack("!I", zlib.crc32(header + timestamp) & 0xFFFFFFFF)

    assert decode_packet(header + timestamp + crc1) is None