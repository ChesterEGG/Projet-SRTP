import pytest
from  src.packet import Packet

def test_packet_creation():
    # Vérifie qu'on peut créer un paquet en Python avec toutes ses infos de base 
    p = Packet(1, 10, 5, 4, 123456, b"test")

    assert p.p_type == 1
    assert p.window == 10
    assert p.seqnum == 5
    assert p.length == 4
    assert p.timestamp == 123456
    assert p.payload == b"test"

def test_encode_decode_roundtrip():
    # Vérifie qu'un paquet encodé redonne bien le même paquet quand on le décdode
    payload = b"hello"
    p = Packet(2, 5, 42, len(payload), 1000, payload)

    encoded = p.encode()
    decoded = Packet.decode(encoded)

    assert decoded is not None
    assert decoded.p_type == p.p_type
    assert decoded.window == p.window
    assert decoded.seqnum == p.seqnum
    assert decoded.length == p.length
    assert decoded.timestamp == p.timestamp
    assert decoded.payload == p.payload

def test_packet_without_payload():
    # Vérifie qu'on peut encoder et décoder un paquet qui ne contient pas de message 
    p = Packet(0, 1, 7, 0, 999)

    encoded = p.encode()
    decoded = Packet.decode(encoded)

    assert decoded is not None
    assert decoded.payload == b""
    assert decoded.length == 0

def test_header_crc_detection():
    # Vérifie que le code rejette un paquet si l'en tete  a été abîmé pendant le trajet
    p = Packet(1, 1, 1, 4, 100, b"data")
    encoded = bytearray(p.encode())

    encoded[0] ^= 0xFF   
    decoded = Packet.decode(bytes(encoded))

    assert decoded is None

def test_payload_crc_detection():
    # Vérifie que le code rejette un paquet si son message a été abîmé pendant le trajet
    p = Packet(1, 1, 1, 4, 100, b"data")
    encoded = bytearray(p.encode())

    encoded[-1] ^= 0xFF   

    decoded = Packet.decode(bytes(encoded))

    assert decoded is None

def test_invalid_length():
    # Vérifie que le code rejette un paquet si son message dépasse la limite de 1024 octets
    p = Packet(1, 1, 1, 2000, 100, b"x"*10)

    encoded = p.encode()

    decoded = Packet.decode(encoded)

    assert decoded is None

def test_packet_too_short():
    # Vérifie que le code rejette les données reçues si elles sont trop courtes 
    data = b"\x00\x01\x02"

    decoded = Packet.decode(data)

    assert decoded is None

def test_max_payload():
    payload = b"x" * 1024

    p = Packet(1, 5, 100, len(payload), 1234, payload)

    encoded = p.encode()
    decoded = Packet.decode(encoded)

    assert decoded is not None
    assert decoded.payload == payload


def test_global():
    # Test pour s'assurer que toutes les informations restent identique après encodage + décodage
    message = b"Message Test"

    original_packet = Packet(
        p_type=1,
        window=5,
        seqnum=42,
        length=len(message),
        timestamp=123456,
        payload=message
    )

    encoded_packet = original_packet.encode()

    decoded_packet = Packet.decode(encoded_packet)

    
    assert decoded_packet is not None
    assert decoded_packet.p_type == original_packet.p_type
    assert decoded_packet.window == original_packet.window
    assert decoded_packet.seqnum == original_packet.seqnum
    assert decoded_packet.timestamp == original_packet.timestamp
    assert decoded_packet.length == original_packet.length
    assert decoded_packet.payload == original_packet.payload
