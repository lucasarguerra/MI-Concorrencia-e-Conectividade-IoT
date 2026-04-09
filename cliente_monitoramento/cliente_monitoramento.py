import socket
import json
import time
import threading
import os

loop = True
loop_1 = True

HOST = os.getenv("SERVIDOR_HOST", "servidor")
TCP_PORT = 12348

# ─── HISTÓRICO PARA GRÁFICO ──────────────────────────────────────────────────

historico = {}
HISTORICO_MAX = 20
lock_historico = threading.Lock()

# ─── CONEXÃO ─────────────────────────────────────────────────────────────────

def conectar_tcp():
    while True:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((HOST, TCP_PORT))
            return sock
        except ConnectionRefusedError:
            print("  Servidor não disponível, tentando em 2s...")
            time.sleep(2)

def enviar_receber(sock, mensagem, tamanho=4096):
    sock.sendall(mensagem.encode())
    return sock.recv(tamanho).decode()

# ─── GRÁFICO ASCII ────────────────────────────────────────────────────────────

def desenhar_grafico(chave, valores, largura=20, altura=5):
    if not valores:
        return
    minv = min(valores)
    maxv = max(valores)
    intervalo = maxv - minv if maxv != minv else 1

    linhas = []
    for row in range(altura, 0, -1):
        threshold = minv + intervalo * (row / altura)
        linha = ""
        for v in valores[-largura:]:
            if v >= threshold:
                linha += "█"
            else:
                linha += " "
        # rótulo lateral
        if row == altura:
            linhas.append(f"  {maxv:>5.1f} │{linha}│")
        elif row == 1:
            linhas.append(f"  {minv:>5.1f} │{linha}│")
        else:
            linhas.append(f"        │{linha}│")

    linhas.append(f"        └{'─' * largura}┘")
    linhas.append(f"         {'últimas leituras':^{largura}}")
    return linhas

# ─── MONITORAMENTO ────────────────────────────────────────────────────────────

monitorando = False
lock_monitor = threading.Lock()

def monitorar():
    global monitorando
    sock_monitor = conectar_tcp()
    while True:
        with lock_monitor:
            ativo = monitorando
        if ativo:
            try:
                resp = enviar_receber(sock_monitor, "LIST:sensores", 4096)
                chaves = json.loads(resp)

                os.system("clear")
                print("╔══════════════════════════════════════════╗")
                print("║       SENSORES EM TEMPO REAL             ║")
                print("║       pressione ENTER para parar         ║")
                print("╚══════════════════════════════════════════╝")
                print()

                for chave in chaves:
                    resp_val = enviar_receber(sock_monitor, f"GET:{chave}")
                    # extrai valor numérico da resposta "chave: valor"
                    try:
                        valor_str = resp_val.split(":")[-1].strip()
                        valor_num = float(valor_str)
                        with lock_historico:
                            if chave not in historico:
                                historico[chave] = []
                            historico[chave].append(valor_num)
                            if len(historico[chave]) > HISTORICO_MAX:
                                historico[chave].pop(0)
                            hist = list(historico[chave])
                    except (ValueError, IndexError):
                        hist = []

                    # ícone por tipo
                    if "temperatura" in chave:
                        icone = "🌡"
                        unidade = "°C"
                    elif "umidade" in chave:
                        icone = "💧"
                        unidade = "%"
                    else:
                        icone = "•"
                        unidade = ""

                    print(f"  {icone}  {chave.upper().replace('_', ' ')} → {resp_val.split(':')[-1].strip()}{unidade}")

                    if hist:
                        linhas_grafico = desenhar_grafico(chave, hist)
                        if linhas_grafico:
                            for linha in linhas_grafico:
                                print(linha)
                    print()

            except Exception as e:
                print(f"  Erro no monitoramento: {e}")
                sock_monitor = conectar_tcp()
            time.sleep(2)
        else:
            time.sleep(0.1)

thread_monitor = threading.Thread(target=monitorar, daemon=True)
thread_monitor.start()

# ─── MENU ─────────────────────────────────────────────────────────────────────

tcp = conectar_tcp()

os.system("clear")
print("╔══════════════════════════════════════════╗")
print("║       SISTEMA ROTA DAS COISAS: IoT       ║")
print("╚══════════════════════════════════════════╝")
input("\n  Pressione ENTER para abrir o menu principal...")

while loop:
    os.system("clear")
    print("╔══════════════════════════════════════════╗")
    print("║              MENU PRINCIPAL              ║")
    print("╠══════════════════════════════════════════╣")
    print("║  [1]  Consultar sensores                 ║")
    print("║  [2]  Enviar comando ao ventilador       ║")
    print("║  [3]  Ver estado dos ventiladores        ║")
    print("║  [4]  Sair do sistema                   ║")
    print("╚══════════════════════════════════════════╝")
    option = input("\n  Digite aqui: ").strip()

    if option == "1":
        print("\n  Monitoramento iniciado. Pressione ENTER para parar.\n")
        with lock_monitor:
            monitorando = True
        input()
        with lock_monitor:
            monitorando = False
        os.system("clear")
        print("  Monitoramento pausado.\n")

    elif option == "2":
        try:
            resp = enviar_receber(tcp, "ID:ventilador", 4096)
            array_vent = json.loads(resp)
        except Exception:
            print("\n  ✗ Servidor não respondeu.")
            tcp = conectar_tcp()
            continue

        if not array_vent:
            print("\n  ✗ Nenhum ventilador conectado.")
            input("\n  Pressione ENTER para continuar...")
            continue

        while loop_1:
            print("\n  Qual ventilador você deseja modificar?")
            for v in array_vent:
                print(f"    [{v}] Ventilador {v}")
            op_escolha = input("\n  Digite aqui: ").strip()
            try:
                op_escolha_int = int(op_escolha)
                if op_escolha_int in array_vent:
                    loop_1 = False
                else:
                    print("  Ventilador não encontrado.")
            except ValueError:
                print("  Digite um número válido.")

        print("\n  [1] Ligar   [2] Desligar")
        op_acao = input("\n  Digite aqui: ").strip()
        if op_acao == "1":
            acao = "LIGAR"
        elif op_acao == "2":
            acao = "DESLIGAR"
        else:
            print("\n  ✗ Opção inválida.")
            loop_1 = True
            input("\n  Pressione ENTER para continuar...")
            continue

        tcp.sendall(f"CMD:ventilador_{op_escolha}:{acao}".encode())
        print(f"\n  ✓ Comando {acao} enviado para ventilador {op_escolha}.")
        loop_1 = True
        input("\n  Pressione ENTER para continuar...")

    elif option == "3":
        try:
            resp = enviar_receber(tcp, "LIST:atuadores", 4096)
            estados = json.loads(resp)
            print()
            if not estados:
                print("  ✗ Nenhum ventilador conectado.")
            else:
                print("  ╔══════════════════════════════════╗")
                print("  ║    ESTADO DOS VENTILADORES       ║")
                print("  ╠══════════════════════════════════╣")
                for nome, estado in estados.items():
                    simbolo = "▶" if estado == "LIGADO" else "■"
                    print(f"  ║  {simbolo}  {nome:<12}  {estado:<12}  ║")
                print("  ╚══════════════════════════════════╝")
        except Exception:
            print("\n  ✗ Servidor não respondeu.")
            tcp = conectar_tcp()
        input("\n  Pressione ENTER para continuar...")

    elif option == "4":
        os.system("clear")
        print("  Encerrando sistema...")
        loop = False

    else:
        print("\n  ✗ Comando inexistente, tente novamente.")
        input("\n  Pressione ENTER para continuar...")

tcp.close()