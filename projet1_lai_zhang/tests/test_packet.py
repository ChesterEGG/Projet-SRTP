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


def test_type_invalide():
    ok = False
    try:
        p = Packet(4, 10, 0, 0, b"abc")
        p.pack()
    except ValueError:
        ok = True
    assert ok

#si window dépaasse la limite
def test_window_invalide():
    ok = False
    try:
        p = Packet(1, 100, 0, 0, b"abc")
        p.pack()
    except ValueError:
        ok = True
    assert ok

#si le numéro de séquence est trop grand
def test_seqnum_invalide():
    ok = False
    try:
        p = Packet(1, 10, 3000, 0, b"abc")
        p.pack()
    except ValueError:
        ok = True
    assert ok


def test_payload_trop_grand():
    ok = False
    try:
        p = Packet(1, 10, 0, 0, b"a" * 2000)
        p.pack()
    except ValueError:
        ok = True
    assert ok


def test_unpack_trop_petit():
    data = b"abc"
    p = Packet.unpack(data)
    assert p is None

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