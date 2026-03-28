import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from encode_decode import Packet, PTYPE_DATA, PTYPE_ACK, PTYPE_SACK


def test_data_avec_payload():
    """Paquet DATA avec payload : encode puis decode doit redonner les mêmes champs."""
    p = Packet(PTYPE_DATA, window=5, length=5, seqnum=0, timestamp=12345, payload=b'hello')
    p2 = Packet.decode(p.encode())
    assert p2 is not None
    assert p2.ptype == PTYPE_DATA
    assert p2.window == 5
    assert p2.seqnum == 0
    assert p2.payload == b'hello'


def test_ack_sans_payload():
    """Paquet ACK sans payload : encode puis decode."""
    p = Packet(PTYPE_ACK, window=3, length=0, seqnum=1, timestamp=0)
    p2 = Packet.decode(p.encode())
    assert p2 is not None
    assert p2.ptype == PTYPE_ACK
    assert p2.seqnum == 1


def test_crc1_corrompu():
    """Un bit corrompu dans le header doit faire retourner None."""
    p = Packet(PTYPE_ACK, window=3, length=0, seqnum=1, timestamp=0)
    data = bytearray(p.encode())
    data[5] ^= 0xFF   # corrompt un octet du header
    assert Packet.decode(bytes(data)) is None


def test_type_invalide():
    """Un paquet avec type=0 doit être ignoré (retourne None)."""
    p = Packet(0, window=0, length=0, seqnum=0, timestamp=0)
    assert Packet.decode(p.encode()) is None


def test_length_trop_grand():
    """Un paquet avec length > 1024 doit être ignoré."""
    p = Packet(PTYPE_DATA, window=5, length=1025, seqnum=0, timestamp=0, payload=b'x' * 1025)
    assert Packet.decode(p.encode()) is None


def test_fin_de_transfert():
    """Paquet DATA avec length=0 = signal de fin de transfert."""
    p = Packet(PTYPE_DATA, window=5, length=0, seqnum=0, timestamp=0)
    p2 = Packet.decode(p.encode())
    assert p2 is not None
    assert p2.length == 0


def test_crc2_corrompu():
    """CRC2 corrompu (dernier octet) doit faire retourner None."""
    p = Packet(PTYPE_DATA, window=5, length=5, seqnum=0, timestamp=0, payload=b'hello')
    data = bytearray(p.encode())
    data[-1] ^= 0xFF
    assert Packet.decode(bytes(data)) is None


def test_sack_valide():
    """Paquet PTYPE_SACK valide : doit être décodé correctement."""
    p = Packet(PTYPE_SACK, window=3, length=0, seqnum=5, timestamp=0)
    p2 = Packet.decode(p.encode())
    assert p2 is not None
    assert p2.ptype == PTYPE_SACK
    assert p2.seqnum == 5


def test_seqnum_max():
    """seqnum=2047 (valeur max sur 11 bits) doit être conservé."""
    p = Packet(PTYPE_DATA, window=0, length=0, seqnum=2047, timestamp=0)
    p2 = Packet.decode(p.encode())
    assert p2 is not None
    assert p2.seqnum == 2047


def test_window_max():
    """window=63 (valeur max sur 6 bits) doit être conservée."""
    p = Packet(PTYPE_ACK, window=63, length=0, seqnum=0, timestamp=0)
    p2 = Packet.decode(p.encode())
    assert p2 is not None
    assert p2.window == 63


def test_payload_tronque():
    """Payload physiquement tronqué dans les bytes reçus doit retourner None."""
    p = Packet(PTYPE_DATA, window=0, length=10, seqnum=0, timestamp=0, payload=b'x' * 10)
    data = p.encode()[:-5]   # on coupe les 5 derniers octets (CRC2 + fin payload)
    assert Packet.decode(data) is None


def test_paquet_trop_court():
    """Moins de 12 bytes = header incomplet, doit retourner None."""
    assert Packet.decode(b'\x00' * 8) is None


def test_timestamp_conserve():
    """Le timestamp doit être conservé intact après encode/decode."""
    ts = 0xDEADBEEF
    p = Packet(PTYPE_DATA, window=0, length=3, seqnum=0, timestamp=ts, payload=b'abc')
    p2 = Packet.decode(p.encode())
    assert p2 is not None
    assert p2.timestamp == ts