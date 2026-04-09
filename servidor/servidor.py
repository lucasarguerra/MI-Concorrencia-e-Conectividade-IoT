import socket
import time
import threading
import json
import queue
import sys

sys.stdout.reconfigure(line_buffering=True)


# locks e contadores pra controlar os ids dos sensores
lock_ids = threading.Lock()
contador_temp = 0
contador_umid = 0
# dicionário que guarda os últimos valores recebidos dos sensores
valores = {}
lock = threading.Lock()
# dicionário de conexões ativas dos atuadores, locks individuais e filas de comando
atuadores = {}
locks_individuais = {}
filas_atuadores = {}
# guarda o estado atual de cada atuador (ligado/desligado) e o timestamp do último sinal
status_atuadores = {}
lock_atuador = threading.Lock()
# listas de ids registrados por tipo
ids_temperatura = []
ids_umidade = []
ids_ventilador = []
# fila compartilhada pra processar os pacotes udp com múltiplos workers
fila_udp = queue.Queue()
NUM_WORKERS_UDP = 4


# ─── SENSORES UDP ────────────────────────────────────────────────────────────

def tratar_sensor(data, addr):
    try:
        mensagem = data.decode()
        payload = json.loads(mensagem)

        # Validação dos campos obrigatórios
        # puxa os campos do payload
        tipo = payload.get("tipo")
        sensor_id = payload.get("id")
        valor = payload.get("valor")
        timestamp_msg = payload.get("timestamp", time.time())
 # descarta se algum campo obrigatório estiver faltando
        if not all([tipo, sensor_id, valor is not None]):
            print(f"Payload inválido de {addr}: {payload}")
            return
  # descarta pacotes com mais de 5 segundos de atraso
        if time.time() - timestamp_msg > 5:
            return
# salva o valor mais recente desse sensor
        chave = f"{tipo}_{sensor_id}"
        with lock:
            valores[chave] = {
                "valor": valor,
                "timestamp": time.time()
            }
        if tipo == "umidade":
            print(f"Umidade {sensor_id} recebida: {valor}%")
        elif tipo == "temperatura":
            print(f"Temperatura {sensor_id} recebida: {valor}°C")
        else:
            print(f"Dado desconhecido [{tipo}]: {valor}")
    except Exception as e:
        print(f"Erro ao tratar sensor: {e}")


def worker_udp():
    # fica em loop pegando pacotes da fila e processando
    while True:
        data, addr = fila_udp.get()
        tratar_sensor(data, addr)
        fila_udp.task_done()


def verificar_sensores():
    while True:
        # roda em background checando se algum sensor parou de mandar dados
        time.sleep(2)
        agora = time.time()
        with lock:
            for chave in list(valores.keys()):
                # se o último dado tem mais de 5s, considera que o sensor caiu
                if agora - valores[chave]["timestamp"] > 5:
                    print(f"{chave} caiu!")

                    partes = chave.split("_", 1)
                    tipo = partes[0]
                    sensor_id = int(partes[1])
                     # remove o id da lista correspondente
                    with lock_ids:
                        if tipo == "temperatura" and sensor_id in ids_temperatura:
                            ids_temperatura.remove(sensor_id)
                        elif tipo == "umidade" and sensor_id in ids_umidade:
                            ids_umidade.remove(sensor_id)

                    del valores[chave]


# ─── ATUADORES TCP ───────────────────────────────────────────────────────────

def loop_tcp():
     # servidor que aceita conexões dos ventiladores
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 12347))
    server.listen(5)
    print("Servidor TCP aguardando ventiladores na porta 12347...")
    while True:
        client_socket, addr = server.accept()
        mensagem = client_socket.recv(1024).decode()
        partes = mensagem.split(":")
        if partes[0] == "CADASTRO" and partes[1] == "ventilador":
            # gera um id sequencial pra esse ventilador
            with lock_atuador:
                atuador_id = (ids_ventilador[-1] + 1) if ids_ventilador else 1
                ids_ventilador.append(atuador_id)
                chave = f"ventilador_{atuador_id}"
                atuadores[chave] = client_socket
                locks_individuais[chave] = threading.Lock()
                filas_atuadores[chave] = queue.PriorityQueue()

               # manda o id de volta pro ventilador
            client_socket.sendall(str(atuador_id).encode())
            print(f"Ventilador '{chave}' conectado.")
               # sobe uma thread pra heartbeat e outra pra processar os comandos
            threading.Thread(target=heartbeat, args=(client_socket, chave), daemon=True).start()
            threading.Thread(target=worker_atuador, args=(chave,), daemon=True).start()


def worker_atuador(chave):
    # consome comandos da fila e manda pro atuador
    while True:
        with lock_atuador:
            fila = filas_atuadores.get(chave)
        if fila is None:
            break
        try:
            timestamp, acao = fila.get(timeout=1)
        except queue.Empty:
             # se a fila tá vazia e o atuador foi removido, encerra
            with lock_atuador:
                if chave not in atuadores:
                    break
            continue
        envio_atuador(chave, acao)
        fila.task_done()


def heartbeat(client_socket, chave):
    # manda PING a cada 3s pra saber se o ventilador ainda tá vivo
    while True:
        time.sleep(3)

        lock_ind = locks_individuais.get(chave)
        if lock_ind is None:
            break

        try:
            with lock_ind:
                client_socket.sendall(b"PING")
                client_socket.settimeout(5)
                resposta = client_socket.recv(1024)
                client_socket.settimeout(None)

                if resposta != b"PONG":
                    break
                 # atualiza o timestamp do último sinal recebido
                with lock_atuador:
                    if chave in status_atuadores:
                        status_atuadores[chave]["timestamp"] = time.time()

        except Exception:
            break
    # chegou aqui: ventilador não respondeu, limpa tudo
    tipo, atuador_id = chave.split("_")
    atuador_id = int(atuador_id)

    with lock_atuador:
        if chave in atuadores:
            try:
                atuadores[chave].close()
            except:
                pass
            del atuadores[chave]
        if chave in locks_individuais:
            del locks_individuais[chave]
        if chave in status_atuadores:
            del status_atuadores[chave]
        if chave in filas_atuadores:
            del filas_atuadores[chave]
        if atuador_id in ids_ventilador:
            ids_ventilador.remove(atuador_id)

    try:
        client_socket.close()
    except:
        pass

    print(f"Ventilador '{chave}' desconectado.")


def verificar_atuadores():
    # checagem periódica baseada em timestamp, complementar ao heartbeat
    while True:
        time.sleep(2)
        agora = time.time()
        with lock_atuador:
            for chave in list(status_atuadores.keys()):
                 # se passou mais de 6s sem atualização, considera morto
                if agora - status_atuadores[chave]["timestamp"] > 6:
                    print(f"{chave} caiu!")
                    if chave in atuadores:
                        try:
                            atuadores[chave].close()
                        except:
                            pass
                        del atuadores[chave]
                    if chave in locks_individuais:
                        del locks_individuais[chave]
                    if chave in status_atuadores:
                        del status_atuadores[chave]
                    if chave in filas_atuadores:
                        del filas_atuadores[chave]
                    tipo, atuador_id = chave.split("_")
                    atuador_id = int(atuador_id)
                    if atuador_id in ids_ventilador:
                        ids_ventilador.remove(atuador_id)


def envio_atuador(chave, acao):
    with lock_atuador:
        conn = atuadores.get(chave)
        lock = locks_individuais.get(chave)
        # manda o comando e espera a confirmação
    if conn is None:
        print(f"Atuador '{chave}' não conectado.")
        return
    try:
        with lock:
            conn.sendall(acao.encode())
            confirmacao = conn.recv(1024).decode()
        estado = confirmacao.split(":")[1]
        # salva o estado atual e atualiza o timestamp
        with lock_atuador:
            status_atuadores[chave] = {
                "estado": estado,
                "timestamp": time.time()
            }
        print(f"{chave} confirmou: {confirmacao}")
    except Exception as e:
        print(f"Erro ao comunicar com {chave}: {e}")


# ─── CLIENTES TCP ─────────────────────────────────────────────────────────────

def tratar_cliente(conn, addr):
    print(f"Cliente conectado: {addr}")
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            mensagem = data.decode()
             # retorna o valor mais recente de um sensor específico
            if mensagem.startswith("GET:"):
                tipo_pedido = mensagem.split(":", 1)[1]
                with lock:
                    dado = valores.get(tipo_pedido)
                if not dado:
                    resposta = f"Nenhum dado de {tipo_pedido} ainda"
                else:
                    resposta = f"{tipo_pedido}: {dado['valor']}"
                conn.sendall(resposta.encode())
            # lista sensores ativos ou atuadores e seus estados
            elif mensagem.startswith("LIST:"):
                tipo_lista = mensagem.split(":")[1]
                if tipo_lista == "sensores":
                    with lock:
                        chaves = list(valores.keys())
                    conn.sendall(json.dumps(chaves).encode())
                elif tipo_lista == "atuadores":
                    with lock_atuador:
                        chaves = {
                            k: status_atuadores.get(k, {}).get("estado", "sem modificação")
                            for k in atuadores
                        }
                    conn.sendall(json.dumps(chaves).encode())
  # retorna os ids registrados de um tipo específico
            elif mensagem.startswith("ID:"):
                tipo_lista = mensagem.split(":")[1]
                if tipo_lista == "ventilador":
                    with lock_atuador:
                        array_vent = json.dumps(ids_ventilador)
                    conn.sendall(array_vent.encode())
                elif tipo_lista == "temperatura":
                    with lock_ids:
                        conn.sendall(json.dumps(ids_temperatura).encode())
                elif tipo_lista == "umidade":
                    with lock_ids:
                        conn.sendall(json.dumps(ids_umidade).encode())
  # enfileira um comando pra um atuador específico
            elif mensagem.startswith("CMD:"):
                partes = mensagem.split(":")
                typ = partes[1]
                acao = partes[2]

                if typ.startswith("ventilador_"):
                    with lock_atuador:
                        fila = filas_atuadores.get(typ)
                    if fila is not None:
                        # Prioridade 0: comandos de controle têm prioridade máxima
                        fila.put((0, acao))
                    else:
                        conn.sendall(f"Atuador '{typ}' não conectado.".encode())
                else:
                    conn.sendall(f"Atuador desconhecido: {typ}".encode())

    except Exception as e:
        print(f"Cliente {addr} desconectado: {e}")
    finally:
        conn.close()
        print(f"Cliente {addr} encerrado.")


def loop_tcp_clientes():
    # servidor que aceita conexões dos clientes (dashboard, testes, etc)
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 12348))
    server.listen(5)
    print("Servidor TCP aguardando clientes na porta 12348...")
    while True:
        conn, addr = server.accept()
        threading.Thread(target=tratar_cliente, args=(conn, addr), daemon=True).start()


# ─── INICIALIZAÇÃO ────────────────────────────────────────────────────────────

for _ in range(NUM_WORKERS_UDP):
    threading.Thread(target=worker_udp, daemon=True).start()
# threads de background pra cada responsabilidade
threading.Thread(target=loop_tcp, daemon=True).start()
threading.Thread(target=verificar_sensores, daemon=True).start()
threading.Thread(target=verificar_atuadores, daemon=True).start()
threading.Thread(target=loop_tcp_clientes, daemon=True).start()
# socket udp principal que recebe registros e dados dos sensores
udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
udp_socket.bind(('0.0.0.0', 12345))
print("Servidor UDP aguardando na porta 12345...")

while True:
    data, addr = udp_socket.recvfrom(1024)
    mensagem = data.decode()

    if mensagem.startswith("REGISTRO:"):
        nome_sensor = mensagem.split(":")[1]
        with lock_ids:
            if nome_sensor == "temperatura":
                contador_temp += 1
                ids_temperatura.append(contador_temp)
                udp_socket.sendto(str(contador_temp).encode(), addr)
            elif nome_sensor == "umidade":
                contador_umid += 1
                ids_umidade.append(contador_umid)
                udp_socket.sendto(str(contador_umid).encode(), addr)
            else:
                print("Sensor desconhecido")
    else:
        fila_udp.put((data, addr))