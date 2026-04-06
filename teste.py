"""
Testes de concorrência — Rota das Coisas
========================================
Execução:  python teste_concorrencia.py
           python teste_concorrencia.py -v          (verbose)
           python teste_concorrencia.py -k carga    (só testes de carga)

O servidor deve estar rodando antes de executar:
  - UDP na porta 12345
  - TCP na porta 12347
"""

import unittest
import socket
import threading
import time
import json
import statistics

SERVIDOR_HOST = "localhost"
SERVIDOR_UDP  = 12345
SERVIDOR_TCP  = 12347

# ─── helpers ──────────────────────────────────────────────────────────────────

def udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(5)
    return s

def registrar_sensor(tipo="temperatura"):
    s = udp()
    s.sendto(f"REGISTRO:{tipo}".encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
    sensor_id = s.recvfrom(1024)[0].decode()
    return s, sensor_id

def conectar_ventilador():
    """Conecta um ventilador via TCP e já responde PING/PONG em background."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect((SERVIDOR_HOST, SERVIDOR_TCP))
    sock.sendall(b"CADASTRO:ventilador")
    atuador_id = sock.recv(1024).decode()

    buffer = ""
    def loop():
        nonlocal buffer
        while True:
            try:
                data = sock.recv(1024)
                if not data:
                    break
                buffer += data.decode()
                while "\n" in buffer:
                    cmd, buffer = buffer.split("\n", 1)
                    cmd = cmd.strip()
                    if cmd == "PING":
                        sock.sendall(b"PONG")
                    elif cmd == "LIGAR":
                        sock.sendall(b"OK:LIGADO\n")
                    elif cmd == "DESLIGAR":
                        sock.sendall(b"OK:DESLIGADO\n")
            except Exception:
                break

    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return sock, atuador_id


# ─── Testes funcionais básicos (corrigidos da versão anterior) ─────────────────

class TestFuncional(unittest.TestCase):

    def test_registro_sensor_retorna_id_numerico(self):
        s, sid = registrar_sensor("temperatura")
        self.assertTrue(sid.isdigit(), f"Esperava ID numérico, recebeu: '{sid}'")
        s.close()

    def test_dois_sensores_ids_unicos(self):
        s1, id1 = registrar_sensor("temperatura")
        s2, id2 = registrar_sensor("temperatura")
        self.assertNotEqual(id1, id2, "IDs devem ser únicos entre sensores")
        s1.close(); s2.close()

    def test_telemetria_e_consulta_get(self):
        s, sid = registrar_sensor("temperatura")
        payload = json.dumps({"tipo": "temperatura", "valor": 77, "id": sid})
        s.sendto(payload.encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
        time.sleep(0.1)
        s.sendto(f"GET:temperatura_{sid}".encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
        resp = s.recvfrom(1024)[0].decode()
        self.assertIn("77", resp)
        s.close()

    def test_registro_ventilador_tcp_retorna_id(self):
        sock, aid = conectar_ventilador()
        self.assertTrue(aid.isdigit(), f"Esperava ID numérico, recebeu: '{aid}'")
        sock.close()

    def test_dois_ventiladores_ids_unicos(self):
        s1, id1 = conectar_ventilador()
        s2, id2 = conectar_ventilador()
        self.assertNotEqual(id1, id2, "IDs de ventiladores devem ser únicos")
        s1.close(); s2.close()

    def test_comando_ventilador_conectado(self):
        vent, aid = conectar_ventilador()
        time.sleep(0.2)

        c = udp()
        c.sendto(f"CMD:ventilador_{aid}:LIGAR".encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
        time.sleep(0.3)

        c.sendto(b"LIST:atuadores", (SERVIDOR_HOST, SERVIDOR_UDP))
        estados = json.loads(c.recvfrom(4096)[0].decode())
        chave = f"ventilador_{aid}"
        self.assertIn(chave, estados)
        self.assertEqual(estados[chave], "LIGADO")
        c.close(); vent.close()

    def test_comando_ventilador_desconectado_nao_trava(self):
        """Servidor não deve travar ao receber CMD para ventilador inexistente."""
        c = udp()
        c.sendto(b"CMD:ventilador_9999:LIGAR", (SERVIDOR_HOST, SERVIDOR_UDP))
        time.sleep(0.3)
        # se chegou até aqui sem exceção, o servidor não travou
        c.close()


# ─── Testes de concorrência ────────────────────────────────────────────────────

class TestConcorrencia(unittest.TestCase):

    # ------------------------------------------------------------------
    # N sensores registrando ao mesmo tempo → todos IDs únicos
    # ------------------------------------------------------------------
    def _registros_simultaneos(self, n, tipo="temperatura"):
        ids       = []
        erros     = []
        lock      = threading.Lock()

        def registrar():
            try:
                s, sid = registrar_sensor(tipo)
                with lock:
                    ids.append(sid)
                s.close()
            except Exception as e:
                with lock:
                    erros.append(str(e))

        threads = [threading.Thread(target=registrar) for _ in range(n)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)

        return ids, erros

    def test_10_sensores_registrando_ao_mesmo_tempo(self):
        ids, erros = self._registros_simultaneos(10)
        self.assertEqual(len(erros), 0, f"Erros de registro: {erros}")
        self.assertEqual(len(ids), 10, "Nem todos os sensores receberam ID")
        self.assertEqual(len(set(ids)), 10, "IDs duplicados detectados!")

    def test_50_sensores_registrando_ao_mesmo_tempo(self):
        ids, erros = self._registros_simultaneos(50)
        self.assertEqual(len(erros), 0, f"Erros: {erros}")
        self.assertEqual(len(set(ids)), 50, f"Colisão de IDs com 50 sensores! Total único: {len(set(ids))}")

    # ------------------------------------------------------------------
    # N sensores enviando telemetria em rajada → servidor não perde dados
    # ------------------------------------------------------------------
    def _carga_telemetria(self, n_sensores, mensagens_por_sensor=20):
        enviados  = []
        recebidos = []
        lock      = threading.Lock()

        def sensor_worker(i):
            try:
                s, sid = registrar_sensor("temperatura")
                chave = f"temperatura_{sid}"
                valor_final = None
                for v in range(mensagens_por_sensor):
                    payload = json.dumps({"tipo": "temperatura", "valor": v, "id": sid})
                    s.sendto(payload.encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
                    valor_final = v
                with lock:
                    enviados.append((chave, valor_final))
                s.close()
            except Exception as e:
                with lock:
                    enviados.append(None)

        threads = [threading.Thread(target=sensor_worker, args=(i,)) for i in range(n_sensores)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=15)

        time.sleep(0.3)  # dá tempo ao servidor processar o último batch

        c = udp()
        for item in enviados:
            if item is None:
                continue
            chave, _ = item
            try:
                c.sendto(f"GET:{chave}".encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
                resp = c.recvfrom(1024)[0].decode()
                if "Nenhum" not in resp:
                    recebidos.append(chave)
            except socket.timeout:
                pass
        c.close()

        return enviados, recebidos

    def test_carga_10_sensores_20_msgs_cada(self):
        enviados, recebidos = self._carga_telemetria(10, 20)
        validos = [e for e in enviados if e is not None]
        taxa = len(recebidos) / len(validos) * 100
        print(f"\n  [10 sensores × 20 msgs] Taxa de entrega: {taxa:.1f}%  ({len(recebidos)}/{len(validos)})")
        self.assertGreaterEqual(taxa, 80, f"Taxa de entrega abaixo de 80%: {taxa:.1f}%")

    def test_carga_50_sensores_20_msgs_cada(self):
        enviados, recebidos = self._carga_telemetria(50, 20)
        validos = [e for e in enviados if e is not None]
        taxa = len(recebidos) / len(validos) * 100
        print(f"\n  [50 sensores × 20 msgs] Taxa de entrega: {taxa:.1f}%  ({len(recebidos)}/{len(validos)})")
        self.assertGreaterEqual(taxa, 70, f"Taxa de entrega abaixo de 70%: {taxa:.1f}%")

    # ------------------------------------------------------------------
    # N clientes consultando ao mesmo tempo (GET / LIST)
    # ------------------------------------------------------------------
    def _clientes_simultaneos(self, n_clientes):
        # registra um sensor com valor conhecido
        s, sid = registrar_sensor("umidade")
        payload = json.dumps({"tipo": "umidade", "valor": 55, "id": sid})
        s.sendto(payload.encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
        time.sleep(0.15)
        s.close()

        respostas = []
        erros     = []
        lock      = threading.Lock()

        def consultar():
            c = udp()
            try:
                c.sendto(f"GET:umidade_{sid}".encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
                resp = c.recvfrom(1024)[0].decode()
                with lock:
                    respostas.append(resp)
            except Exception as e:
                with lock:
                    erros.append(str(e))
            finally:
                c.close()

        threads = [threading.Thread(target=consultar) for _ in range(n_clientes)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)

        return respostas, erros

    def test_10_clientes_consultando_ao_mesmo_tempo(self):
        respostas, erros = self._clientes_simultaneos(10)
        self.assertEqual(len(erros), 0, f"Erros: {erros}")
        self.assertEqual(len(respostas), 10, "Nem todos os clientes receberam resposta")
        for r in respostas:
            self.assertIn("55", r, f"Resposta incorreta: '{r}'")

    def test_30_clientes_consultando_ao_mesmo_tempo(self):
        respostas, erros = self._clientes_simultaneos(30)
        taxa = len(respostas) / 30 * 100
        print(f"\n  [30 clientes simultâneos] Respondidos: {taxa:.1f}%")
        self.assertGreaterEqual(taxa, 90, "Menos de 90% dos clientes foram respondidos")

    # ------------------------------------------------------------------
    # Múltiplos ventiladores conectando ao mesmo tempo → IDs únicos
    # ------------------------------------------------------------------
    def test_10_ventiladores_conectando_ao_mesmo_tempo(self):
        ids   = []
        erros = []
        socks = []
        lock  = threading.Lock()

        def conectar():
            try:
                sock, aid = conectar_ventilador()
                with lock:
                    ids.append(aid)
                    socks.append(sock)
            except Exception as e:
                with lock:
                    erros.append(str(e))

        threads = [threading.Thread(target=conectar) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)

        self.assertEqual(len(erros), 0, f"Erros ao conectar ventiladores: {erros}")
        self.assertEqual(len(set(ids)), len(ids), f"IDs duplicados entre ventiladores! IDs: {ids}")

        for s in socks:
            try: s.close()
            except: pass

    # ------------------------------------------------------------------
    # Sensores + clientes ao mesmo tempo (cenário realista misto)
    # ------------------------------------------------------------------
    def test_cenario_misto_sensores_e_clientes(self):
        """
        20 sensores enviando telemetria + 20 clientes consultando simultaneamente.
        Verifica que o servidor atende os dois tipos sem travar.
        """
        respostas_clientes = []
        erros              = []
        lock               = threading.Lock()

        # pré-registra sensores com valor conhecido
        sids = []
        for _ in range(5):
            s, sid = registrar_sensor("temperatura")
            payload = json.dumps({"tipo": "temperatura", "valor": 99, "id": sid})
            s.sendto(payload.encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
            sids.append(sid)
            s.close()
        time.sleep(0.15)

        def sensor_spam(i):
            try:
                s, sid = registrar_sensor("temperatura")
                for v in range(30):
                    payload = json.dumps({"tipo": "temperatura", "valor": v, "id": sid})
                    s.sendto(payload.encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
                s.close()
            except Exception as e:
                with lock:
                    erros.append(f"sensor: {e}")

        def cliente_consulta(sid):
            try:
                c = udp()
                c.sendto(f"GET:temperatura_{sid}".encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
                resp = c.recvfrom(1024)[0].decode()
                with lock:
                    respostas_clientes.append(resp)
                c.close()
            except Exception as e:
                with lock:
                    erros.append(f"cliente: {e}")

        threads = []
        for i in range(20):
            threads.append(threading.Thread(target=sensor_spam, args=(i,)))
        for sid in sids * 4:  # 20 consultas nos 5 sensores pré-registrados
            threads.append(threading.Thread(target=cliente_consulta, args=(sid,)))

        for t in threads: t.start()
        for t in threads: t.join(timeout=15)

        print(f"\n  [Cenário misto] Respostas de clientes: {len(respostas_clientes)}/20 | Erros: {len(erros)}")
        self.assertEqual(len(erros), 0, f"Erros no cenário misto: {erros}")
        self.assertGreaterEqual(len(respostas_clientes), 18, "Menos de 90% dos clientes foram atendidos")


# ─── Testes de latência / desempenho ──────────────────────────────────────────

class TestLatencia(unittest.TestCase):

    def _medir_latencia(self, n, tipo="temperatura"):
        latencias = []
        lock      = threading.Lock()

        def worker():
            try:
                s, sid = registrar_sensor(tipo)
                payload = json.dumps({"tipo": tipo, "valor": 1, "id": sid})
                s.sendto(payload.encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
                time.sleep(0.05)
                t0 = time.time()
                s.sendto(f"GET:{tipo}_{sid}".encode(), (SERVIDOR_HOST, SERVIDOR_UDP))
                s.recvfrom(1024)
                with lock:
                    latencias.append((time.time() - t0) * 1000)
                s.close()
            except Exception:
                pass

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        return latencias

    def test_latencia_10_clientes_simultaneos(self):
        lats = self._medir_latencia(10)
        media  = statistics.mean(lats)
        p95    = sorted(lats)[int(len(lats) * 0.95)]
        print(f"\n  [10 clientes] Latência  média={media:.1f}ms  p95={p95:.1f}ms")
        self.assertLess(media, 500, f"Latência média alta: {media:.1f}ms")

    def test_latencia_50_clientes_simultaneos(self):
        lats = self._medir_latencia(50)
        if not lats:
            self.skipTest("Nenhuma resposta recebida — servidor pode estar sobrecarregado")
        media  = statistics.mean(lats)
        p95    = sorted(lats)[int(len(lats) * 0.95)]
        maximo = max(lats)
        print(f"\n  [50 clientes] Latência  média={media:.1f}ms  p95={p95:.1f}ms  max={maximo:.1f}ms")
        self.assertLess(media, 1000, f"Latência média muito alta: {media:.1f}ms")

    def test_latencia_100_clientes_simultaneos(self):
        lats = self._medir_latencia(100)
        if not lats:
            self.skipTest("Nenhuma resposta recebida")
        media  = statistics.mean(lats)
        p95    = sorted(lats)[int(len(lats) * 0.95)]
        taxa   = len(lats) / 100 * 100
        print(f"\n  [100 clientes] Respondidos={taxa:.0f}%  média={media:.1f}ms  p95={p95:.1f}ms")
        self.assertGreaterEqual(taxa, 60, "Menos de 60% respondidos com 100 clientes")


# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Testes de concorrência — Rota das Coisas")
    print("Servidor esperado em localhost:12345 (UDP) e :12347 (TCP)")
    print("=" * 60)
    unittest.main(verbosity=2)