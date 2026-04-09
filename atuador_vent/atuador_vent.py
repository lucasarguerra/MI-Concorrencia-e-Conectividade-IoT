import socket
import time
import os

SERVIDOR_HOST = os.getenv("SERVIDOR_HOST", "servidor")
SERVIDOR_PORT = 12347

while True:
    try:
        print("Tentando conectar ao servidor...")

        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.connect((SERVIDOR_HOST, SERVIDOR_PORT))

        tcp_socket.settimeout(5)  # 🔥 ESSENCIAL

        tcp_socket.sendall("CADASTRO:ventilador".encode())
        resposta = tcp_socket.recv(1024).decode()
        atuador_id = resposta

        print(f"Ventilador {atuador_id} registrado.")

        while True:
            try:
                data = tcp_socket.recv(1024)

                if not data:
                    print("Servidor desconectado.")
                    break

                comando = data.decode()

                if comando == "PING":
                    tcp_socket.sendall(b"PONG")

                elif comando == "LIGAR":
                    tcp_socket.sendall("OK:LIGADO".encode())

                elif comando == "DESLIGAR":
                    tcp_socket.sendall("OK:DESLIGADO".encode())

            except socket.timeout:
                # timeout bateu sem nenhum ping, reconecta
                print("Sem resposta (timeout). Reconectando...")
                break

    except Exception as e:
        print(f"Erro de conexão: {e}")

    time.sleep(3)