# Sistema IoT — Rota das Coisas

Sistema distribuído de monitoramento com sensores de temperatura e umidade, ventiladores como atuadores e um cliente de monitoramento em tempo real.

---

## Arquitetura geral

O sistema é composto por cinco tipos de componentes que se comunicam de forma independente:

```
[sensor_temp]  ──UDP──┐
[sensor_umid]  ──UDP──┤──► [servidor] ──TCP──► [atuador_vent]
                       └──────────────TCP──────► [cliente]
```

Cada componente roda em seu próprio container Docker e se comunica com o servidor central via rede interna. Os sensores usam UDP por ser leve e tolerante a perda de pacotes; os atuadores e clientes usam TCP por precisarem de entrega garantida e estado de conexão.

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

O ventilador conecta via TCP na porta 12347 e manda uma mensagem de `CADASTRO:ventilador`. O servidor registra a conexão, gera um ID e devolve pro atuador. A partir daí o ventilador fica em modo passivo esperando comandos: responde `PONG` nos pings de heartbeat, `OK:LIGADO` no comando `LIGAR` e `OK:DESLIGADO` no comando `DESLIGAR`. Se a conexão cair por qualquer motivo, o atuador tenta reconectar automaticamente a cada 3 segundos.

### Cliente de monitoramento (`cliente_monitoramento.py`)

O cliente conecta na porta 12348 e oferece um menu interativo no terminal com quatro funções:

- **Monitorar sensores em tempo real** — consulta todos os sensores ativos a cada 2 segundos e exibe um gráfico ASCII no terminal com as últimas 20 leituras de cada sensor
- **Enviar comando ao ventilador** — lista os ventiladores conectados e permite mandar `LIGAR` ou `DESLIGAR` para um específico
- **Ver estado dos ventiladores** — exibe o estado atual (ligado/desligado) de todos os ventiladores
- **Sair**

O monitoramento em tempo real roda numa thread separada, permitindo que o terminal seja retomado pelo usuário a qualquer momento ao pressionar ENTER.

### Protocolo de comunicação (porta 12348)

Os clientes se comunicam com o servidor usando um protocolo textual simples:

| Comando | Resposta | Descrição |
|---------|----------|-----------|
| `REGISTRO:<tipo>` | ID numérico | Registra um sensor e recebe um ID |
| `GET:<tipo>_<id>` | `<tipo>_<id>: <valor>` | Último valor de um sensor |
| `LIST:sensores` | JSON array de chaves | Sensores ativos |
| `LIST:atuadores` | JSON objeto com estados | Atuadores e seus estados |
| `ID:ventilador` | JSON array de IDs | IDs dos ventiladores conectados |
| `CMD:<chave>:<acao>` | — | Enfileira um comando para um atuador |

---

## Rodando em uma única máquina (Docker Compose)

Clone o repositório e suba tudo com:

```bash
docker compose up
```

Isso já sobe o servidor, os sensores, o ventilador e o cliente juntos na mesma rede interna do Docker.

Para entrar no cliente interativo depois que os containers estiverem rodando:

```bash
docker attach <nome_do_container_cliente>
```

---

## Rodando em máquinas separadas

Nesse caso você usa `docker run` direto, passando o IP do servidor pela variável de ambiente `SERVIDOR_HOST`.

**Primeiro sobe o servidor na máquina dele:**

```bash
docker run -d -p 12345:12345/udp -p 12347:12347 -p 12348:12348 lucasarguerra/pblredes-servidor:1.0
```

**Depois, nas outras máquinas, sobe os sensores, o atuador e o cliente apontando pro IP do servidor:**

```bash
docker run -d -e SERVIDOR_HOST=172.16.103.12 lucasarguerra/pblredes-sensor_temp:1.0
docker run -d -e SERVIDOR_HOST=172.16.103.12 lucasarguerra/pblredes-sensor_umidade:1.0
docker run -d -e SERVIDOR_HOST=172.16.103.12 lucasarguerra/pblredes-atuador_vent:1.0
docker run -it -e SERVIDOR_HOST=172.16.103.12 lucasarguerra/pblredes-cliente_monitoramento:1.0
```

> Substitua `172.16.103.12` pelo IP real da máquina onde o servidor está rodando.  
> O cliente usa `-it` porque precisa de terminal interativo para o menu funcionar.

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

## O que o cliente consegue fazer

- Monitorar todos os sensores ativos em tempo real com gráfico ASCII
- Ver o estado atual de cada ventilador (ligado/desligado)
- Mandar comando de ligar ou desligar para um ventilador específico
- Listar todos os sensores e atuadores conectados no momento

---

## Decisões de implementação

**UDP para sensores** — sensores mandam dados em alta frequência (intervalo de 1ms no código atual) e uma leitura perdida ocasionalmente não é crítica. UDP elimina o overhead de conexão e confirmação, sendo mais adequado para telemetria contínua.

**TCP para atuadores e clientes** — comandos de controle precisam de entrega garantida. Um `LIGAR` ou `DESLIGAR` perdido teria consequências reais, então TCP é a escolha correta aqui.

**Heartbeat ativo** — em vez de depender só de exceções de socket, o servidor verifica ativamente se cada ventilador ainda está vivo. Isso detecta casos onde a conexão "parece" ativa mas o processo do outro lado travou ou foi encerrado abruptamente.

**PriorityQueue por atuador** — os comandos são enfileirados com prioridade, permitindo que comandos urgentes (prioridade 0) sejam processados antes de outros. Também garante que comandos não se percam mesmo se o atuador estiver ocupado processando outro.

**Workers UDP** — o pool de 4 threads para processar pacotes UDP evita que o loop principal de recepção bloqueie enquanto processa um pacote mais lento. Pacotes continuam sendo recebidos enquanto os anteriores ainda estão sendo tratados.

**Locks individuais por conexão** — cada atuador tem seu próprio lock além do lock global. Isso permite que comandos para ventiladores diferentes sejam enviados em paralelo sem contenção desnecessária.
