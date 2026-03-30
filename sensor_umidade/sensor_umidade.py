import socket
import random
import time
import json



udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
address = ('servidor', 12345)
udp_socket.sendto("REGISTRO:umidade".encode(), address)
resposta, addr = udp_socket.recvfrom(1024)
sensor_id = resposta.decode()
print(f"ID recebido: {sensor_id}")
while True:
    message = random.randint(0,100)
    payload = json.dumps({"tipo": "umidade", "valor": message,"id":sensor_id})
    udp_socket.sendto(payload.encode(), address)
    print(f"Umidade enviada: {message}")
    time.sleep(0.5)


udp_socket.close()