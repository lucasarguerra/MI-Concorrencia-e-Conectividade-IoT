import socket
import json
import time
import threading
import os

loop = True
loop_1 = True

HOST = os.getenv("SERVIDOR_HOST", "servidor")
TCP_PORT = 12348

def conectar_tcp():
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((HOST, TCP_PORT))
            return sock
        except ConnectionRefusedError:
            print("Servidor não disponível, tentando em 2s...")
            time.sleep(2)

def enviar_receber(sock, mensagem, tamanho=4096):
    sock.sendall(mensagem.encode())
    return sock.recv(tamanho).decode()

monitorando = False
lock_monitor = threading.Lock()

def monitorar():
    sock_monitor = conectar_tcp()
    while True:
        with lock_monitor:
            ativo = monitorando
        if ativo:
            try:
                resp = enviar_receber(sock_monitor, "LIST:sensores", 4096)
                chaves = json.loads(resp)
                print("\n--- SENSORES EM TEMPO REAL ---")
                for chave in chaves:
                    resp = enviar_receber(sock_monitor, f"GET:{chave}")
                    print(f"  {resp}")
                print("  (pressione ENTER para parar)")
            except Exception as e:
                print(f"Erro no monitoramento: {e}")
                sock_monitor = conectar_tcp()
            time.sleep(2)
        else:
            time.sleep(0.1)

thread_monitor = threading.Thread(target=monitorar, daemon=True)
thread_monitor.start()

tcp = conectar_tcp()

print("SISTEMA ROTA DAS COISAS: IOT")
input("Clique enter para a abertura do menu principal")

while loop:
    print("=" * 14)
    print("MENU PRINCIPAL")
    print("=" * 14)
    print("[1] Consultar sensores")
    print("[2] Enviar comando ao ventilador")
    print("[3] Ver estado dos ventiladores")
    print("[4] Sair do sistema")
    option = input("Digite aqui: ")

    if option == "1":
        print("\nMonitoramento iniciado. Pressione ENTER para parar.\n")
        with lock_monitor:
            monitorando = True
        input()
        with lock_monitor:
            monitorando = False
        print("Monitoramento pausado.\n")

    elif option == "2":
        try:
            resp = enviar_receber(tcp, "ID:ventilador", 4096)
            array_vent = json.loads(resp)
        except Exception:
            print("Servidor não respondeu.")
            tcp = conectar_tcp()
            continue

        if not array_vent:
            print("Nenhum ventilador conectado.")
            continue

        while loop_1:
            print("Qual ventilador você deseja modificar?")
            for v in array_vent:
                print(f"[{v}] Ventilador {v}")
            op_escolha = input("Digite aqui: ")
            try:
                op_escolha_int = int(op_escolha)
                if op_escolha_int in array_vent:
                    loop_1 = False
            except ValueError:
                print("Digite um número válido.")

        print("[1] Ligar  [2] Desligar")
        op_acao = input("Digite aqui: ")
        if op_acao == "1":
            acao = "LIGAR"
        elif op_acao == "2":
            acao = "DESLIGAR"
        else:
            print("Opção inválida.")
            loop_1 = True
            continue

        tcp.sendall(f"CMD:ventilador_{op_escolha}:{acao}".encode())
        print(f"Comando {acao} enviado para ventilador {op_escolha}.")
        loop_1 = True

    elif option == "3":
        try:
            resp = enviar_receber(tcp, "LIST:atuadores", 4096)
            estados = json.loads(resp)
            if not estados:
                print("Nenhum ventilador conectado.")
            else:
                print("\n--- ESTADO DOS VENTILADORES ---")
                for nome, estado in estados.items():
                    print(f"  {nome}: {estado}")
        except Exception:
            print("Servidor não respondeu.")
            tcp = conectar_tcp()

    elif option == "4":
        print("Encerrando sistema...")
        loop = False
    else:
        print("Você digitou um comando inexistente, tente novamente.")

tcp.close()