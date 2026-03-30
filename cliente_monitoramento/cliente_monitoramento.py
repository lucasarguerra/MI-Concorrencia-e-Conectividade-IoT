import socket
import json
import time
import threading

loop = True
loop_1 = True
loop_2 = True

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
address = ('servidor', 12345)
udp_socket.bind(('0.0.0.0', 12346))
udp_socket.settimeout(5)


monitor_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
monitor_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
monitor_socket.bind(('0.0.0.0', 12349))
monitor_socket.settimeout(3)

monitorando = False
lock_monitor = threading.Lock()

def monitorar():
    while True:
        with lock_monitor:
            ativo = monitorando
        
        if ativo:
            try:
                # pede a lista de sensores
                monitor_socket.sendto("LIST:sensores".encode(), address)
                data, _ = monitor_socket.recvfrom(4096)
                chaves = json.loads(data.decode())
                
                print("\n--- SENSORES EM TEMPO REAL ---")
                for chave in chaves:
                    monitor_socket.sendto(f"GET:{chave}".encode(), address)
                    data, _ = monitor_socket.recvfrom(1024)
                    print(f"  {data.decode()}")
                print("  (pressione ENTER para parar)")
            except socket.timeout:
                pass
            time.sleep(2)
        else:
            time.sleep(0.1)

thread_monitor = threading.Thread(target=monitorar, daemon=True)
thread_monitor.start()

print("SISTEMA ROTA DAS COISAS: IOT")
input("Clique enter para a abertura do menu principal")
#aa
while loop:
    print("=" * 14)
    print("MENU PRINCIPAL")
    print("=" * 14)
    print("[1] Consultar sensores")
    print("[2] Enviar comando aos atuadores")
    print("[3] Consultar estado dos atuadores")
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
        print("Qual atuador?")
        print("[1] Ventilador")
        print("[2] Alarme")
        op_atu = input("Digite aqui: ")

        if op_atu == "1":
            nome = "ventilador"
            udp_socket.sendto(f"ID:{nome}".encode(), address)
            
            try:
                data, addr = udp_socket.recvfrom(4096)
                array_vent = json.loads(data.decode())
            except socket.timeout:
                print("Servidor não respondeu. Verifique se está rodando.")

            while loop_1 == True:
                print("Qual atuador você deseja modificar ?")
                for i in range(0,len(array_vent)):
                    print(f"[{array_vent[i]}]Atuador {array_vent[i]}")
                op_escolha = input("Digite aqui:")
                op_escolha_int = int(op_escolha)
                if op_escolha_int in array_vent:
                    loop_1 = False  

            print("[1] Ligar  [2] Desligar")
            op_acao = input("Digite aqui: ")
            if op_acao == "1":
                acao = "LIGAR"
            elif op_acao == "2":
                acao = "DESLIGAR"
            else:
                print("Opção inválida.")
                continue

        elif op_atu == "2":
            nome = "alarme"
            udp_socket.sendto(f"ID:{nome}".encode(), address)
            try:
                data, addr = udp_socket.recvfrom(4096)
                array_alm = json.loads(data.decode())
            except socket.timeout:
                print("Servidor não respondeu. Verifique se está rodando.")



            while loop_2 == True:
                print("Qual atuador você deseja modificar ?")
                for i in range(0,len(array_alm)):
                    print(f"[{array_alm[i]}]Atuador {array_alm[i]}")
                op_escolha = input("Digite aqui:")
                op_escolha_int = int(op_escolha)
                if op_escolha_int in array_alm:
                    loop_2 = False    


            print("[1] Tocar  [2] Silenciar")
            op_acao = input("Digite aqui: ")
            if op_acao == "1":
                acao = "TOCAR"
            elif op_acao == "2":
                acao = "SILENCIAR"
            else:
                print("Opção inválida.")
                continue
        else:
            print("Opção inválida.")
            continue

        udp_socket.sendto(f"CMD:{nome}_{op_escolha}:{acao}".encode(), address)
        print(f"Comando {acao} enviado para {nome} {op_escolha}.")

    elif option == "3":
        udp_socket.sendto("LIST:atuadores".encode(), address)
        try:
            data, addr = udp_socket.recvfrom(4096)
            estados = json.loads(data.decode())
            if not estados:
                print("Nenhum atuador conectado.")
            else:
                print("\n--- ESTADO DOS ATUADORES ---")
                for nome, estado in estados.items():
                    print(f"  {nome}: {estado}")
        except socket.timeout:
            print("Servidor não respondeu. Verifique se está rodando.")

    elif option == "4":
        print("Encerrando sistema...")
        loop = False
    else:
        print("Você digitou um comando inexistente, tente novamente.")

udp_socket.close()