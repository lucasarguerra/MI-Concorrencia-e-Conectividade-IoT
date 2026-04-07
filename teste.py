import socket
import threading
import time

def cliente(nome, comando):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 12348))
    print(f"{nome} enviando: {comando}")
    sock.sendall(comando.encode())
    time.sleep(0.1)
    sock.close()

n = int(input("Digite quantos comandos alternados você deseja enviar:"))
threads = []
for i in range(n):
    if i % 2 == 0:
        acao = "LIGAR"
    else:
        acao = "DESLIGAR"
    t = threading.Thread(
        target=cliente,
        args=(f"Cliente {i}", f"CMD:ventilador_1:{acao}")
    )
    threads.append(t)

for t in threads:
    t.start()
for t in threads:
    t.join()

print("Todos os comandos enviados. Verifique o estado final no servidor.")