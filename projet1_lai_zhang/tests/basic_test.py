

#test

pak1 = Packet(1, 9, 67, 0, b"juste un testes")
pak2 = Packet(1, 10, 133, 1, b'c est cense print 67')


print(pak1)

pak3 = Packet.unpack(pak2.pack())

if pak3:
    print(f"Unpack réussi ! Type: {pak3.type}, Seq: {pak3.seqnum}, Payload: {pak3.payload.decode()}")
else:
    print("Échec de l'unpack")