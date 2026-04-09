# Sistema IoT — Rota das Coisas

Sistema distribuído de monitoramento com sensores de temperatura e umidade, ventiladores como atuadores e um cliente de monitoramento em tempo real.

---

## Estrutura de diretórios

```
pblredes/
├── servidor/
│   ├── servidor.py
│   └── Dockerfile
├── sensor_temp/
│   ├── sensor_temp.py
│   └── Dockerfile
├── sensor_umidade/
│   ├── sensor_umidade.py
│   └── Dockerfile
├── atuador_vent/
│   ├── atuador_vent.py
│   └── Dockerfile
├── cliente_monitoramento/
│   ├── cliente_monitoramento.py
│   └── Dockerfile
└── docker-compose.yml
```

---

## Pacotes e dependências

O projeto usa apenas bibliotecas da **biblioteca padrão do Python 3.12** — nenhuma dependência externa precisa ser instalada:

| Biblioteca | Uso |
|------------|-----|
| `socket` | Comunicação UDP e TCP |
| `threading` | Concorrência entre sensores, atuadores e clientes |
| `json` | Serialização dos payloads |
| `time` | Timestamps e delays |
| `queue` | Fila de pacotes UDP e comandos de atuadores |
| `os` | Leitura de variáveis de ambiente e limpeza de tela |
| `random` | Geração de valores simulados nos sensores |

---

## Arquitetura geral

```
[sensor_temp]  ──UDP──┐
[sensor_umid]  ──UDP──┴──► [servidor] ──TCP──► [atuador_vent]
                                 │
                                 └──TCP──► [cliente_monitoramento]
```

Cada componente roda em seu próprio container Docker e se comunica com o servidor central. Os sensores usam UDP por ser leve e tolerante a perda de pacotes; os atuadores e clientes usam TCP por precisarem de entrega garantida e estado de conexão.

---

## Como funciona

### Servidor (`servidor.py`)

O servidor é o centro de tudo. Ele abre três portas em paralelo usando threads:

- **12345 UDP** — recebe registros e dados dos sensores (temperatura e umidade)
- **12347 TCP** — aceita conexão dos ventiladores (atuadores)
- **12348 TCP** — aceita conexão dos clientes de monitoramento

Internamente, o servidor usa um pool de 4 workers para processar os pacotes UDP em paralelo, evitando gargalo quando vários sensores mandam dados ao mesmo tempo. Cada valor recebido é guardado em um dicionário com timestamp, e uma thread de background verifica a cada 2 segundos se algum sensor parou de enviar dados — se o último pacote tiver mais de 5 segundos, o sensor é considerado inativo e removido da lista.

Para os atuadores, o servidor mantém uma `PriorityQueue` por ventilador, um lock individual por conexão e uma thread de heartbeat dedicada. O heartbeat manda `PING` a cada 3 segundos e aguarda `PONG`; se não receber, o ventilador é removido automaticamente e todos os seus recursos são liberados.

### Sensores (`sensor_temp.py` e `sensor_umidade.py`)

Ao subir, cada sensor manda uma mensagem de `REGISTRO` pro servidor via UDP e aguarda receber um ID único (inteiro sequencial). A partir daí, fica em loop mandando leituras aleatórias no formato JSON:

```json
{"tipo": "temperatura", "valor": 42, "id": "1", "timestamp": 1713456789.12}
```

O servidor descarta automaticamente qualquer pacote com timestamp mais de 5 segundos no passado, protegendo contra filas acumuladas ou reenvios tardios.

### Atuador (`atuador_vent.py`)

O ventilador conecta via TCP na porta 12347 e manda `CADASTRO:ventilador`. O servidor registra a conexão, gera um ID e devolve pro atuador. A partir daí o ventilador fica em modo passivo esperando comandos: responde `PONG` nos pings de heartbeat, `OK:LIGADO` no comando `LIGAR` e `OK:DESLIGADO` no comando `DESLIGAR`. Se a conexão cair por qualquer motivo, o atuador tenta reconectar automaticamente a cada 3 segundos.

### Cliente de monitoramento (`cliente_monitoramento.py`)

O cliente conecta diretamente ao servidor na porta 12348 e oferece um menu interativo no terminal com quatro funções:

- **Monitorar sensores em tempo real** — consulta todos os sensores ativos a cada 2 segundos e exibe um gráfico ASCII no terminal com as últimas 20 leituras de cada sensor
- **Enviar comando ao ventilador** — lista os ventiladores conectados e permite mandar `LIGAR` ou `DESLIGAR` para um específico
- **Ver estado dos ventiladores** — exibe o estado atual (ligado/desligado) de todos os ventiladores
- **Sair**

O monitoramento em tempo real roda numa thread separada, permitindo que o terminal seja retomado pelo usuário a qualquer momento ao pressionar ENTER.

### Protocolo de comunicação (porta 12348)

Os clientes se comunicam com o servidor usando um protocolo textual simples:

| Comando | Resposta | Descrição |
|---------|----------|-----------|
| `GET:<tipo>_<id>` | `<tipo>_<id>: <valor>` | Último valor de um sensor |
| `LIST:sensores` | JSON array de chaves | Sensores ativos |
| `LIST:atuadores` | JSON objeto com estados | Atuadores e seus estados |
| `ID:ventilador` | JSON array de IDs | IDs dos ventiladores conectados |
| `CMD:<chave>:<acao>` | — | Enfileira um comando para um atuador |

---

## Dockerfile

Cada componente tem seu próprio Dockerfile. Todos seguem a mesma estrutura, variando apenas o script copiado e executado. Exemplo do atuador:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY atuador_vent.py .
CMD ["python", "atuador_vent.py"]
```

Nenhuma instalação adicional de pacotes é necessária pois o projeto usa exclusivamente a biblioteca padrão do Python.

---

## Como executar

### Pré-requisitos

- Dockerinstalado
- Docker Compose instalado (já incluso no Docker Desktop)

### Rodando em uma única máquina (Docker Compose)

Clone o repositório e suba tudo com:

```bash
git clone https://github.com/lucasarguerra/pblredes
cd pblredes
docker compose up
```

Isso já sobe o servidor, os sensores, o ventilador e o cliente juntos na mesma rede interna do Docker.

### Acessando o cliente interativo

Com os containers rodando, abra o terminal do cliente com:

```bash
docker exec -it pblredes-cliente_monitoramento-1 bash
```

Dentro do container, execute o cliente:

```bash
python cliente_monitoramento.py
```

---

## Rodando em máquinas separadas

Nesse caso você usa `docker run` direto, passando o IP do servidor pela variável de ambiente `SERVIDOR_HOST`.

**Primeiro suba o servidor na máquina dele:**

```bash
docker run -d -p 12345:12345/udp -p 12347:12347 -p 12348:12348 lucasarguerra/pblredes-servidor:1.0
```

**Depois, nas outras máquinas, suba os sensores, o atuador e o cliente apontando pro IP do servidor:**

```bash
docker run -d -e SERVIDOR_HOST=172.16.103.12 lucasarguerra/pblredes-sensor_temp:1.0
docker run -d -e SERVIDOR_HOST=172.16.103.12 lucasarguerra/pblredes-sensor_umidade:1.0
docker run -d -e SERVIDOR_HOST=172.16.103.12 lucasarguerra/pblredes-atuador_vent:1.0
docker run -d -e SERVIDOR_HOST=172.16.103.12 lucasarguerra/pblredes-cliente_monitoramento:1.0
```

> `172.16.103.12` representa o IP real da máquina onde o servidor está rodando.

Para acessar o cliente após subir o container:

```bash
docker exec -it <nome_ou_id_do_container_cliente> bash
python cliente_monitoramento.py
```

---

## Como usar o cliente

Ao abrir o cliente, você verá o menu principal:

```
╔══════════════════════════════════════════╗
║              MENU PRINCIPAL              ║
╠══════════════════════════════════════════╣
║  [1]  Consultar sensores                 ║
║  [2]  Enviar comando ao ventilador       ║
║  [3]  Ver estado dos ventiladores        ║
║  [4]  Sair do sistema                    ║
╚══════════════════════════════════════════╝
```

**Opção 1 — Consultar sensores:** inicia o monitoramento em tempo real. O terminal exibe o valor atual de cada sensor com um gráfico ASCII das últimas leituras. Pressione ENTER para voltar ao menu.

**Opção 2 — Enviar comando ao ventilador:** lista os ventiladores conectados no momento e pede que você escolha um pelo ID. Em seguida, escolha `LIGAR` ou `DESLIGAR`. O comando é enfileirado e enviado ao atuador com confirmação.

**Opção 3 — Ver estado dos ventiladores:** exibe uma tabela com todos os ventiladores conectados e seus estados atuais (`LIGADO` ou `DESLIGADO`).

**Opção 4 — Sair:** encerra o cliente.

---

## Imagens disponíveis no Docker Hub

| Imagem | Função |
|--------|--------|
| `lucasarguerra/pblredes-servidor:1.0` | Servidor central |
| `lucasarguerra/pblredes-sensor_temp:1.0` | Sensor de temperatura |
| `lucasarguerra/pblredes-sensor_umidade:1.0` | Sensor de umidade |
| `lucasarguerra/pblredes-atuador_vent:1.0` | Ventilador (atuador) |
| `lucasarguerra/pblredes-cliente_monitoramento:1.0` | Cliente de monitoramento |

---

## Portas utilizadas

| Porta | Protocolo | Uso |
|-------|-----------|-----|
| 12345 | UDP | Registro e dados dos sensores |
| 12347 | TCP | Conexão dos ventiladores |
| 12348 | TCP | Conexão dos clientes |

---

## Decisões de implementação

**UDP para sensores** — sensores mandam dados em alta frequência e uma leitura perdida ocasionalmente não é crítica. UDP elimina o overhead de conexão e confirmação, sendo mais adequado para telemetria contínua.

**TCP para atuadores e clientes** — comandos de controle precisam de entrega garantida. Um `LIGAR` ou `DESLIGAR` perdido teria consequências reais, então TCP é a escolha correta aqui.

**Heartbeat ativo** — em vez de depender só de exceções de socket, o servidor verifica ativamente se cada ventilador ainda está vivo. Isso detecta casos onde a conexão "parece" ativa mas o processo do outro lado travou ou foi encerrado abruptamente.

**PriorityQueue por atuador** — os comandos são enfileirados com prioridade, permitindo que comandos urgentes sejam processados antes de outros. Também garante que comandos não se percam mesmo se o atuador estiver ocupado processando outro.

**Workers UDP** — o pool de 4 threads para processar pacotes UDP evita que o loop principal de recepção bloqueie enquanto processa um pacote mais lento. Pacotes continuam sendo recebidos enquanto os anteriores ainda estão sendo tratados.

**Locks individuais por conexão** — cada atuador tem seu próprio lock além do lock global. Isso permite que comandos para ventiladores diferentes sejam enviados em paralelo sem contenção desnecessária.
