import socket
import threading
import time

def cliente(nome, comando):
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.settimeout(5)
    address = ('localhost', 12345)
    
    print(f"{nome} mandando: {comando}")
    udp.sendto(comando.encode(), address)
    udp.close()

# cria duas threads que mandam ao mesmo tempo
t1 = threading.Thread(target=cliente, args=("Cliente A", "CMD:ventilador_1:DESLIGAR"))
t2 = threading.Thread(target=cliente, args=("Cliente B", "CMD:ventilador_1:LIGAR"))

t1.start()
t2.start()

t1.join()
t2.join()

print("Ambos mandaram o comando.")