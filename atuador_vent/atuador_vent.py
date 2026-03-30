import socket 

SERVIDOR_HOST = 'localhost'
SERVIDOR_PORT = 12347 


tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
while True:
    try:
        tcp_socket.connect((SERVIDOR_HOST, SERVIDOR_PORT))
        break 
    except ConnectionRefusedError:
        print("Servidor não disponível, tentando novamente em 2s...")
        time.sleep(2)
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
tcp_socket.sendall("CADASTRO:ventilador".encode())
resposta = tcp_socket.recv(1024).decode()
atuador_id = resposta
print(f'Alarme {atuador_id} conectado ao servidor, aguardando comandos...')
print("Ventilador conectado ao servidor. Aguardando comandos...")

estado = "DESLIGADO"

while True:
    try:
        data = tcp_socket.recv(1024)

        if not data:
            print("Servidor desconectado")
            break
        comando = data.decode()
        print(f"Comando recebido:{comando}")
        if comando == "LIGAR":
            estado = "LIGADO"
            print("Ventilador LIGADO ")
            tcp_socket.sendall("OK:LIGADO".encode())
        elif comando == "DESLIGAR":
            estado = "DESLIGADO"
            print("Ventilador DESLIGADO ")
            tcp_socket.sendall("OK:DESLIGADO".encode())
        else:
            print(f"Comando desconhecido: {comando}")
            tcp_socket.sendall("ERRO:COMANDO_INVALIDO".encode())

    except ConnectionResetError:
        print("Conexão com servidor perdida.")
        break

tcp_socket.close()
print("Ventilador encerrado.")
