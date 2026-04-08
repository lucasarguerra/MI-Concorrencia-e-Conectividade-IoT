import socket
import random
import time
import json
import os 

# 🔥 pega host e porta por variável de ambiente
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

host = os.getenv("SERVIDOR_HOST", "servidor")
address = (host, 12345)
udp_socket.sendto("REGISTRO:temperatura".encode(), address)
resposta, addr = udp_socket.recvfrom(1024)
sensor_id = resposta.decode()

print(f"ID recebido: {sensor_id}")

while True:
    
    message = random.randint(0,100)
    payload = json.dumps({"tipo": "temperatura", "valor": message, "id": sensor_id, "timestamp": time.time()})
    udp_socket.sendto(payload.encode(), address)
    print(f"Temperatura enviada: {message}")
    time.sleep(0.001)
        


udp_socket.close()