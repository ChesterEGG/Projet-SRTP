import struct
import zlib

PTYPE_DATA = 1
PTYPE_ACK  = 2
PTYPE_SACK = 3

class Packet:
    def __init__(self, ptype, window, length, seqnum, timestamp, payload=b''):
        self.ptype     = ptype
        self.window    = window
        self.length    = length
        self.seqnum    = seqnum
        self.timestamp = timestamp
        self.payload   = payload

    def encode(self):
        # on utilise << pour placer chaque champ au bon endroit puis | pour les fusionner
        first_word = (self.ptype  << 30) | (self.window << 24) | (self.length << 11) | (self.seqnum)

        # on convertit first_word (4 bytes) et timestamp (4 bytes) en bytes bruts big-endian --> 8 bytes
        header= struct.pack("!II", first_word, self.timestamp)
        crc1 = zlib.crc32(header) & 0xFFFFFFFF # ça assure que ce nombre tient bien sur 32 bits (4 bytes)
        header_with_crc = header + struct.pack("!I", crc1)

        if self.payload:
            crc2 = zlib.crc32(self.payload) & 0xFFFFFFFF 
            return header_with_crc + self.payload + struct.pack("!I", crc2)
        else :
            return header_with_crc

    @staticmethod
    def decode(data):
        # on doit avoir minimum 12 bytes (header avec crc1)
        if len(data) < 12:
            return None

        first_word, timestamp, crc1_received = struct.unpack("!III", data[:12]) 
        crc1_computed = zlib.crc32(data[:8]) & 0xFFFFFFFF
        if crc1_computed != crc1_received:
            print(crc1_computed)
            return None

        ptype  = (first_word >> 30) & 0x3
        window = (first_word >> 24) & 0x3F
        length = (first_word >> 11) & 0x1FFF
        seqnum = (first_word) & 0x7FF

        # type inconnu donc on ignore
        if ptype == 0:       
            return None
        # length trop grand donc on ignore
        if length > 1024:   
            return None

        payload = data[12:12 + length]

        # gestion d'une erreur de troncation
        if len(payload)!=length:
            return None

        # on check crc2 pour voir si le payload est le même 
        if length > 0 and len(data) >= 12 + length + 4:
            crc2_received = struct.unpack("!I", data[12 + length:12 + length + 4])[0] # on extrait les 4 bytes de crc2
            crc2_computed = zlib.crc32(payload) & 0xFFFFFFFF
            if crc2_computed != crc2_received:
                return None

        return Packet(ptype, window, length, seqnum, timestamp, payload)
