import socket
import time
import threading
import json
import pickle 

valores = {}
lock = threading.Lock()

atuadores = {}
status_atuadores = {}
lock_atuador = threading.Lock()

ids_temperatura = []
ids_umidade = []

ids_alarme = []
ids_ventilador = []

locks_individuais = {}


def tratar_sensor(data, addr):
    mensagem = data.decode()
    if ":" not in mensagem:
        print(f"Mensagem inválida de {addr}: {mensagem}")
        return
    payload = json.loads(mensagem)
    tipo = payload["tipo"]
    sensor_id = payload["id"]
    valor = payload["valor"]
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


def verificar_sensores():
    while True:
        time.sleep(2)
        agora = time.time()
        with lock:
            for chave in list(valores.keys()):
                if agora - valores[chave]["timestamp"] > 5:
                    print(f"{chave} caiu!")

                    tipo, sensor_id = chave.split("_")
                    sensor_id = int(sensor_id)

                    if tipo == "temperatura":
                        if sensor_id in ids_temperatura:
                            ids_temperatura.remove(sensor_id)
                    elif tipo == "umidade":
                        if sensor_id in ids_umidade:
                            ids_umidade.remove(sensor_id)

                    del valores[chave]

def manipulacao_atuador(client_socket, tipo_atuador):
    print(f"Atuador '{tipo_atuador}' conectado.")
    while True:
        try:
            client_socket.settimeout(2)
            client_socket.send(b'')
            time.sleep(1)
        except Exception:
            break

    tipo, atuador_id = tipo_atuador.split("_")
    atuador_id = int(atuador_id)

    with lock_atuador:
        atuadores[tipo_atuador] = None
        if tipo == "alarme" and atuador_id in ids_alarme:
            ids_alarme.remove(atuador_id)
        elif tipo == "ventilador" and atuador_id in ids_ventilador:
            ids_ventilador.remove(atuador_id)

    client_socket.close()
    print(f"Atuador '{tipo_atuador}' desconectado.")


def loop_tcp():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', 12347))
    server.listen(5)
    print("Servidor TCP aguardando atuadores na porta 12347...")
    while True:
        client_socket, addr = server.accept()
        mensagem_atuador = client_socket.recv(1024).decode()
        decodificacao_mensagem = mensagem_atuador.split(":")
        tipo_atuador = decodificacao_mensagem[1]

        if decodificacao_mensagem[0] == "CADASTRO":
            if tipo_atuador == "alarme":
                atuador_id = len(ids_alarme) + 1
                ids_alarme.append(atuador_id)
                client_socket.sendall(f"{atuador_id}".encode())
            elif tipo_atuador == "ventilador":
                atuador_id = len(ids_ventilador) + 1
                ids_ventilador.append(atuador_id)
                client_socket.sendall(f"{atuador_id}".encode())
            with lock_atuador:
                atuadores[f"{tipo_atuador}_{atuador_id}"] = client_socket
                locks_individuais[f"{tipo_atuador}_{atuador_id}"] = threading.Lock()
            t = threading.Thread(target=manipulacao_atuador, args=(client_socket, f"{tipo_atuador}_{atuador_id}"), daemon=True)
            t.start()


def envio_atuador(mensagem, addr):
    tipo_atuador = mensagem.split(":")[1]
    acao = mensagem.split(":")[2]

    with lock_atuador:
        conn = atuadores.get(tipo_atuador)
        lock = locks_individuais.get(tipo_atuador)

    if conn is None:
        print(f"Atuador '{tipo_atuador}' não conectado.")
        return  

    try:
        with lock:
            conn.sendall(acao.encode())
            confirmacao = conn.recv(1024).decode()

        estado = confirmacao.split(":")[1]
        status_atuadores[tipo_atuador] = estado
        print(f"{tipo_atuador} confirmou: {confirmacao}")

    except Exception as e:
        print(f"Erro ao comunicar com {tipo_atuador}: {e}")
        atuadores[tipo_atuador] = None


thread_tcp = threading.Thread(target=loop_tcp, daemon=True)
thread_tcp.start()

thread_verifica = threading.Thread(target=verificar_sensores, daemon=True)
thread_verifica.start()

udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
udp_socket.bind(('0.0.0.0', 12345))
print("Servidor UDP aguardando na porta 12345...")

while True:
    data, addr = udp_socket.recvfrom(1024)
    mensagem = data.decode()

    if mensagem.startswith("GET:"):
        tipo_pedido = mensagem.split(":", 1)[1]

        with lock:
            dado = valores.get(tipo_pedido)

        if not dado:
            resposta = f"Nenhum dado de {tipo_pedido} ainda"
        else:
            resposta = f"{tipo_pedido}: {dado['valor']}"

        udp_socket.sendto(resposta.encode(), addr)

    elif mensagem.startswith("STATUS:"):
        nome_atuador = mensagem.split(":", 1)[1]
        with lock_atuador:
            estado = status_atuadores.get(nome_atuador)
        resposta = estado if estado else f"Nenhuma modificação em {nome_atuador} ainda"
        udp_socket.sendto(resposta.encode(), addr)

    elif mensagem.startswith("CMD:"):
        addr_cliente = addr
        thread_cmd = threading.Thread(
            target=envio_atuador,
            args=(mensagem, addr_cliente),
            daemon=True
        )
        thread_cmd.start()

    elif mensagem.startswith("REGISTRO:"):
        nome_sensor = mensagem.split(":")[1]

        if nome_sensor == "temperatura":
            id_temp = len(ids_temperatura) + 1
            ids_temperatura.append(id_temp)
            udp_socket.sendto(str(id_temp).encode(), addr)

        elif nome_sensor == "umidade":
            id_umid = len(ids_umidade) + 1
            ids_umidade.append(id_umid)
            udp_socket.sendto(str(id_umid).encode(), addr)

        else:
            print("Dado desconhecido")

    elif mensagem.startswith("LIST:"):
        tipo_lista = mensagem.split(":")[1]
        if tipo_lista == "sensores":
            with lock:
                chaves = list(valores.keys())
        elif tipo_lista == "atuadores":
            with lock_atuador:
                chaves = {k: status_atuadores.get(k, "sem modificação") 
                        for k, v in atuadores.items() if v is not None}
        resposta = json.dumps(chaves)
        udp_socket.sendto(resposta.encode(), addr)


    elif mensagem.startswith("ID:"):
        tipo_lista = mensagem.split(":")[1]
        if tipo_lista == "ventilador":
            array_vent = json.dumps(ids_ventilador)
            udp_socket.sendto(array_vent.encode(), addr)
        elif tipo_lista == "alarme":
            array_alm = json.dumps(ids_alarme)
            udp_socket.sendto(array_alm.encode(), addr)

    else:
        thread = threading.Thread(target=tratar_sensor, args=(data, addr), daemon=True)
        thread.start()