import struct
import zlib

class Packet:
    # Le constructeur de la classe qui va nous servir à créer les paquets à envoyer
    def __init__(self, p_type, window, seqnum, length, timestamp, payload = bytes()):
        self.p_type = p_type
        self.window = window
        self.length = length
        self.seqnum = seqnum
        self.timestamp = timestamp
        self.payload = payload

    def encode(self):
        #Préparation des mots en décallant les bits à leur position respective
        type_shifted = self.p_type<<30
        window_shifted = self.window<<24
        length_shifted = self.length<< 11
        seqnum_shifted = self.seqnum
        # On assemble le mot
        first_word = type_shifted | window_shifted | length_shifted | seqnum_shifted
        # Pack(le premier mot + le timestamp)
        header_base =struct.pack("!II", first_word, self.timestamp)
        # Calcul du premier CRC sur l'entête de base
        crc1 = zlib.crc32(header_base)
        header = header_base + struct.pack("!I",crc1)
        
        #On gère le payload si il existe en calculant le deuxieme CRC et en l'ajoutant à la fin du paquet
        if self.length > 0:
            crc2 = zlib.crc32(self.payload)
            crc2_packed = struct.pack("!I", crc2)
            
            return header+self.payload+crc2_packed
        else:
            return header

    @classmethod
    def decode(cls, data):
        #on vérifie si le format est correct
        if len(data) < 12:
            return None
            
        #On décode les 12 premiers octets qui contiennent 3 entiers de 32 bits
        valeurs_entete = struct.unpack("!III", data[:12])
        first_word = valeurs_entete[0]
        timestamp = valeurs_entete[1]
        crc1 = valeurs_entete[2]
        #vérification de si l'entete est corrompue en recalculant le CRC1 et en le comparant à celui reçu
        header_base = data[:8]
        calculated_crc1 = zlib.crc32(header_base)
        if calculated_crc1 != crc1:
            return None
        
        # On récupère chaque champ en utilisant des masques binaires
        p_type = (first_word >> 30) & 0x3
        window = (first_word >> 24) & 0x3F
        length = (first_word >> 11) & 0x1FFF
        seqnum = first_word & 0x7FF
        
        # on vérifie si le payload est trop long
        if length > 1024:
            return None
        
        #Extraction du payload et vérification du deuxième CRC
        payload = bytes()
        if length > 0:
            # On vérifie qu'on a bien reçu toutes les données attendues ainsi que les 4 octets du CRC2
            if len(data) < 16 + length:
                return None
            payload = data[12:12+length]
            
            #Le CRC2 se trouve juste après le payload
            crc2_bytes = data[12+length:16+length]
            actual_crc2 = struct.unpack("!I", crc2_bytes)[0]
            calculated_crc2 = zlib.crc32(payload)
            
            #Vérification de si le payload est corrompu
            if calculated_crc2 != actual_crc2:
                return None
        return  cls(p_type, window, seqnum, length, timestamp, payload)