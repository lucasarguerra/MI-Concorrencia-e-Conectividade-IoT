import socket
import time
import threading
import json
import queue
import sys

sys.stdout.reconfigure(line_buffering=True)

lock_ids = threading.Lock()
contador_temp = 0
contador_umid = 0

valores = {}
lock = threading.Lock()

atuadores = {}
locks_individuais = {}
filas_atuadores = {}

status_atuadores = {}
lock_atuador = threading.Lock()

ids_temperatura = []
ids_umidade = []
ids_ventilador = []

fila_udp = queue.Queue()
NUM_WORKERS_UDP = 4


# ─── SENSORES UDP ────────────────────────────────────────────────────────────

def tratar_sensor(data, addr):
    try:
        mensagem = data.decode()
        payload = json.loads(mensagem)

        # Validação dos campos obrigatórios
        tipo = payload.get("tipo")
        sensor_id = payload.get("id")
        valor = payload.get("valor")
        timestamp_msg = payload.get("timestamp", time.time())

        if not all([tipo, sensor_id, valor is not None]):
            print(f"Payload inválido de {addr}: {payload}")
            return

        if time.time() - timestamp_msg > 5:
            return

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
    while True:
        data, addr = fila_udp.get()
        tratar_sensor(data, addr)
        fila_udp.task_done()


def verificar_sensores():
    while True:
        time.sleep(2)
        agora = time.time()
        with lock:
            for chave in list(valores.keys()):
                if agora - valores[chave]["timestamp"] > 5:
                    print(f"{chave} caiu!")

                    partes = chave.split("_", 1)
                    tipo = partes[0]
                    sensor_id = int(partes[1])
                    with lock_ids:
                        if tipo == "temperatura" and sensor_id in ids_temperatura:
                            ids_temperatura.remove(sensor_id)
                        elif tipo == "umidade" and sensor_id in ids_umidade:
                            ids_umidade.remove(sensor_id)

                    del valores[chave]


# ─── ATUADORES TCP ───────────────────────────────────────────────────────────

def loop_tcp():
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
            with lock_atuador:
                atuador_id = (ids_ventilador[-1] + 1) if ids_ventilador else 1
                ids_ventilador.append(atuador_id)
                chave = f"ventilador_{atuador_id}"
                atuadores[chave] = client_socket
                locks_individuais[chave] = threading.Lock()
                filas_atuadores[chave] = queue.PriorityQueue()

            client_socket.sendall(str(atuador_id).encode())
            print(f"Ventilador '{chave}' conectado.")

            threading.Thread(target=heartbeat, args=(client_socket, chave), daemon=True).start()
            threading.Thread(target=worker_atuador, args=(chave,), daemon=True).start()


def worker_atuador(chave):
    while True:
        with lock_atuador:
            fila = filas_atuadores.get(chave)
        if fila is None:
            break
        try:
            timestamp, acao = fila.get(timeout=1)
        except queue.Empty:
            with lock_atuador:
                if chave not in atuadores:
                    break
            continue
        envio_atuador(chave, acao)
        fila.task_done()


def heartbeat(client_socket, chave):
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

                with lock_atuador:
                    if chave in status_atuadores:
                        status_atuadores[chave]["timestamp"] = time.time()

        except Exception:
            break

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
    while True:
        time.sleep(2)
        agora = time.time()
        with lock_atuador:
            for chave in list(status_atuadores.keys()):
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
    if conn is None:
        print(f"Atuador '{chave}' não conectado.")
        return
    try:
        with lock:
            conn.sendall(acao.encode())
            confirmacao = conn.recv(1024).decode()
        estado = confirmacao.split(":")[1]
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

            if mensagem.startswith("GET:"):
                tipo_pedido = mensagem.split(":", 1)[1]
                with lock:
                    dado = valores.get(tipo_pedido)
                if not dado:
                    resposta = f"Nenhum dado de {tipo_pedido} ainda"
                else:
                    resposta = f"{tipo_pedido}: {dado['valor']}"
                conn.sendall(resposta.encode())

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

threading.Thread(target=loop_tcp, daemon=True).start()
threading.Thread(target=verificar_sensores, daemon=True).start()
threading.Thread(target=verificar_atuadores, daemon=True).start()
threading.Thread(target=loop_tcp_clientes, daemon=True).start()

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