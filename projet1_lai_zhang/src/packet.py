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

    @staticmethod
    def unpack(packet):
        """
        Unpack un packet STPR
        :param data: Les bytes du packet
        :return: Un objet Packet ou None si invalide
        """

        if (len(packet) < 12):
            print("packet invalide (trop petit)")
            return None

        # Extration du header et crc1
        line1, timestamp, crc1 = struct.unpack('!III', packet[0:12])
        header = packet[0:8]

        # Vérification du crc1
        expected_crc1 = zlib.crc32(header) & 0xffffffff

        if (crc1 != expected_crc1):
            print("packet invalide (CRC1 incorrect)")
            return None

        # Analyse de la première ligne
        line1_bin = format(line1, '032b')

        type = int(line1_bin[0:2], 2)
        window = int(line1_bin[2:8], 2)
        length = int(line1_bin[8:21], 2)
        seqnum = int(line1_bin[21:32], 2)

        if type not in [1, 2, 3]:
            print("packet invalide (type invalide)")
            return None

        if (window > 63):
            print("packet invalide (window invalide)")
            return None

        if (length > 1024):
            print("packet invalide (packet trop grand)")
            return None

        if seqnum > 2047:
            print("packet invalide (seqnum invalide)")
            return None

        # Extraction des données
        data = b''
        if length > 0:
            data = packet[12:12 + length]

            # Vérification du crc2
            if len(packet) < 12 + length + 4:
                print("packet invalide (payload ou crc2 manquant)")
                return None

            crc2 = struct.unpack('!I', packet[12 + length: 16 + length])[0]
            expected_crc2 = zlib.crc32(data) & 0xffffffff
            if (crc2 != expected_crc2):
                print("packet invalide (CRC2 invalide)")
                return None

        return Packet(type, window, seqnum, timestamp, data)

    def __str__(self):
        """
        Affiche le paquet de façon lisible pour le debugging
        Réalisé avec IA
        """
        p_type_name = {1: "DATA", 2: "ACK", 3: "SACK"}.get(self.type, "UNKNOWN")

        # On prépare un résumé
        res = f"--- [SRTP Packet {p_type_name}] ---\n"
        res += f"Seqnum: {self.seqnum} | Window: {self.window}\n"
        res += f"Payload Length: {len(self.payload)} bytes\n"
        res += f"Timestamp: {self.timestamp}\n"

        # On ajoute le HEX du paquet complet (très utile pour Wireshark)
        packet_bytes = self.pack()
        res += f"Raw Hex: {packet_bytes.hex()}\n"
        res += "---------------------------"
        return res

