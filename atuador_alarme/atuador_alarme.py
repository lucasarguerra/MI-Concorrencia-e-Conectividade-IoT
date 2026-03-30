import socket
import time 
SERVER_HOST = 'localhost'
SERVER_PORT = 12347 

client = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
while True:
    try:
        client.connect((SERVER_HOST, SERVER_PORT))
        break  
    except ConnectionRefusedError:
        print("Servidor não disponível, tentando novamente em 2s...")
        time.sleep(2)
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.sendall("CADASTRO:alarme".encode())
resposta = client.recv(1024).decode()
atuador_id = resposta
print(f'Alarme {atuador_id} conectado ao servidor, aguardando comandos...')
estado = "SILÊNCIO"
if atuador_id == "NAO":
    print("Não foi possível criar outro atuador, são aceitos apenas dois.")
else:
    while True:
        try:
            response = client.recv(4096)
            if not response:
                print("Servidor desconectado")
                break
            comando = response.decode()
            print(f"Comando recebido:{comando}")
            if comando == "TOCAR":
                estado = "TOCANDO"
                print("Alarme tocando")
                client.sendall("OK:TOCANDO".encode())
            elif comando == "SILENCIAR":
                estado = "SILÊNCIO"
                print("Alarme não está tocando")
                client.sendall("OK:SILENCIADO".encode())
            else:
                print(f"Comando desconhecido: {comando}")
                client.sendall("ERRO:COMANDO_INVALIDO".encode())

        except ConnectionResetError:
            print("Conexão com servidor perdida.")
            break

    client.close()
    print("Alarme desconectado.")