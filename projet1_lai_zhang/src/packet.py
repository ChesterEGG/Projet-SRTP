import struct
import zlib

class Packet:

    def __init__(self, type, window, seqnum, timestamp, payload=b''):
        """
        :param ptype: 1=DATA, 2=ACK, 3=SACK
        :param window: Taille fenêtre [0,63]
        :param seqnum: Numéro de séquence [0, 2047]
        :param timestamp:
        :param payload: Données [0, 1024]
        """
        self.type = type
        self.window = window
        self.seqnum = seqnum
        self.timestamp = timestamp
        self.payload = payload if isinstance(payload, bytes) else payload.encode('utf-8')

    def pack(self):
        """
        Créer un packet STPR
        :return: Packet STPR en bytes
        """

        # Créer la première ligne du packet (4 octets)
        line1 = ""

        # Définir le type au deux premier bits
        if self.type not in [1, 2, 3]:
            raise ValueError("Mauvais type de packet")
        if (self.type == 1):
            line1 += "01"
        elif (self.type == 2):
            line1 += "10"
        elif (self.type == 3):
            line1 += "11"

        # Définir le windows au 6 prochain bit
        if (self.window < 0) or (self.window > 63):
            raise ValueError("window pas valide [0, 63]")
        bin_window = format(self.window, '06b')
        line1 += bin_window

        # Définir le length au 13 prochain bits
        length = len(self.payload)
        if length > 1024:
            raise ValueError("Packet trop grand (> à 1024).")
        bin_length = format(length, '013b')
        line1 += bin_length

        # Définir seqnum au 11 prochain bits
        if (self.seqnum < 0) or (self.seqnum > 2047):
            raise ValueError("seqnum pas valide [0, 2047]")
        bin_seqnum = format(self.seqnum, '011b')
        line1 += bin_seqnum

        # Transformation de la 1ere ligne en int
        line1_int = int(line1, 2)

        # Transformer les 2 première lignes en 4octets
        head1 = struct.pack('!I',line1_int)
        head2 = struct.pack('!I',self.timestamp)

        # Calcul du crc1 + version finale du header
        crc_head = head1 + head2
        crc1 = zlib.crc32(crc_head) & 0xffffffff
        head_final = crc_head + struct.pack('!I',crc1)

        # Ajout du payload et crc2
        if length > 0:
            crc2 = zlib.crc32(self.payload) & 0xffffffff
            return head_final + self.payload + struct.pack('!I',crc2)
        else:
            return head_final


#test

pak1 = Packet(1, 0, 0, 0, b"")

test = pak1.pack()
print(len(test))
print(test.hex())
