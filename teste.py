import socket
import threading
import time
import random
import os

loop = True

def cliente(nome, comando):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    host = os.getenv("SERVIDOR_HOST", "localhost")
    sock.connect(("localhost", 12348))

    print(f"{nome} enviando: {comando}")
    sock.sendall(comando.encode())
    time.sleep(0.1)
    sock.close()



while loop:
    print("=" * 20)
    print("" * 5 +"MENU TESTE" + "" * 5)
    print("=" * 20)
    print("[1] Testar concorrência atuadores")
    print("[2] Testar concorrência sensores")
    print("[3] Sair do sistema.")
    op = input("Digite aqui: ")
    if op == "1":
        print("[1] Testar com comandos alternados.")
        print("[2] Testar com comandos contínuos.")
        op_1 = input("digite aqui:")
        if op_1 == "1":
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

        elif op_1 == "2":
            n = int(input("Digite quantos comandos alternados você deseja enviar:"))
            threads = []
            nomes = ["LIGAR", "DESLIGAR"]
            acao = random.choice(nomes)
            print(f"A ação sorteada foi:{acao}")
            for i in range(n):
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


    elif op == "3":
        loop = False
    