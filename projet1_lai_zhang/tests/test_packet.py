import pytest

from src.packet import Packet

#créer un paquet puis unpack
def test_packet_normal():
    p = Packet(1, 10, 5, 123, b"hello")
    data = p.pack()
    p2 = Packet.unpack(data)
    assert p2 is not None
    assert p2.type == 1
    assert p2.window == 10
    assert p2.seqnum == 5
    assert p2.timestamp == 123
    assert p2.payload == b"hello"

#payload vide
def test_packet_vide():
    p = Packet(1, 5, 0, 10, b"")
    data = p.pack()
    p2 = Packet.unpack(data)
    assert p2 is not None
    assert p2.type == 1
    assert p2.window == 5
    assert p2.seqnum == 0
    assert p2.timestamp == 10
    assert p2.payload == b""

def test_payload_string_auto_encode():
    """Vérifie que la classe convertit automatiquement les strings en bytes."""
    p = Packet(1, 10, 0, 0, "Ceci est une string")
    data = p.pack()
    p2 = Packet.unpack(data)
    assert p2.payload == b"Ceci est une string"

def test_limites_max():
    """Vérifie que le paquet accepte les valeurs maximales autorisées par le protocole."""
    # Window max = 63, Seqnum max = 2047, Payload max = 1024
    p = Packet(1, 63, 2047, 999999, b"a" * 1024)
    data = p.pack()
    p2 = Packet.unpack(data)
    assert p2.window == 63
    assert p2.seqnum == 2047
    assert len(p2.payload) == 1024


def test_type_invalide():
    with pytest.raises(ValueError):
        p = Packet(4, 10, 0, 0, b"abc")
        p.pack()

def test_window_invalide():
    with pytest.raises(ValueError):
        p = Packet(1, 100, 0, 0, b"abc")
        p.pack()

def test_seqnum_invalide():
    with pytest.raises(ValueError):
        p = Packet(1, 10, 3000, 0, b"abc")
        p.pack()

def test_payload_trop_grand():
    with pytest.raises(ValueError):
        p = Packet(1, 10, 0, 0, b"a" * 2000)
        p.pack()


def test_unpack_trop_petit():
    data = b"abc"
    p = Packet.unpack(data)
    assert p is None

def test_crc1_header_detection():
    """Vérifie que le paquet est rejeté si le header (CRC1) est corrompu."""
    p_bytes = Packet(1, 32, 10, 0, b"Data").pack()
    corrupted = bytearray(p_bytes)
    # On modifie un octet dans les 8 premiers octets (le header avant le CRC1)
    corrupted[2] = (corrupted[2] + 1) % 256
    assert Packet.unpack(bytes(corrupted)) is None

def test_crc2_payload_detection():
    """Vérifie que le paquet est rejeté si le payload (CRC2) est corrompu."""
    p_bytes = Packet(1, 32, 10, 0, b"Valide").pack()
    corrupted = bytearray(p_bytes)
    # On modifie un octet du payload (index 12 et plus)
    corrupted[15] = (corrupted[15] + 1) % 256
    assert Packet.unpack(bytes(corrupted)) is None

#test affichage text paquet data
def test_str_data():
    p = Packet(1, 10, 5, 123, b"hello")
    s = str(p)
    assert "DATA" in s
    assert "5" in s
    assert "10" in s
    assert "123" in s

#test affichage text paquet ack
def test_str_ack():
    p = Packet(2, 7, 9, 50, b"")
    s = str(p)
    assert "ACK" in s
    assert "9" in s

#test affichage text paquet sack
def test_str_sack():
    p = Packet(3, 6, 2, 11, b"")
    s = str(p)
    assert "SACK" in s
    assert "2" in s