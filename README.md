# MiniPresidente

Compartilhamento de tela peer-to-peer para redes locais (LAN) ou VPNs. Qualquer pessoa na mesma rede cria ou entra numa sala e transmite sua tela ao mesmo tempo — como o Discord, mas sem servidor central.

## Funcionalidades

- **Descoberta automática de peers** via broadcast UDP em LAN física
- **Descoberta via VPN** com unicast para seed peers + gossip automático
- **Transmissão de tela em tempo real** — JPEG sobre TCP, captura via `mss` (Windows, Linux e Mac)
- **Grid de telas lado a lado** — assista as telas de todos os membros da sala
- **Preview local** — veja sua própria tela sendo transmitida
- **Interface gráfica** — lobby + janela da sala com grid de telas e lista de membros
- **Empacotamento** — executável standalone via PyInstaller
- **Auto-update** — verificação automática de atualizações via GitHub Releases (Windows frozen)

## Como instalar (terminal)

Precisa de **Python 3.10+**.

```bash
# Clonar
git clone https://github.com/ioNeXd/MiniPresidente.git
cd MiniPresidente

# Criar e ativar ambiente virtual
python -m venv venv

# Windows:
venv\Scripts\activate

# Linux / Mac:
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Rodar
python -m app.main
```

Cada amigo roda o mesmo comando na própria máquina. Digite o mesmo **nome de sala** pra todo mundo cair junto.

## Executável (.exe)

Para quem não tem Python instalado, a forma canônica de compilar é:

```bash
pip install pyinstaller
pyinstaller MiniPresidente.spec
```

Isso garante nome de saída e `hidden-imports` consistentes. O executável fica em `dist/MiniPresidente.exe`.

Alternativa via linha de comando:

```bash
pyinstaller --onefile --windowed --name="MiniPresidente" --hidden-import=PySide6.QtSvg app/main.py
```

## Descoberta de peers

### LAN física (broadcast)
Em rede local, o broadcast UDP para `255.255.255.255` faz a descoberta automática — basta todos estarem na mesma subnet.

### VPN (Radmin / Hamachi)
O broadcast UDP **não funciona** em VPNs como Radmin e Hamachi (o tráfego broadcast não é encaminhado). Para contornar isso, o programa usa **descoberta por unicast com seed peers**:

1. O usuário informa o **IP de pelo menos um peer** na tela inicial (campo "IPs de peers")
2. O programa envia anúncios diretamente para esses IPs via unicast
3. A partir daí, o **gossip automático** propaga: quando um peer aprende sobre outros peers, passa a anunciar para eles também
4. Todos na VPN recebem os anúncios mesmo sem broadcast

**Como usar em VPN:**
1. Instale a VPN e conecte-se à rede dos amigos
2. Abra o programa — o campo **IP anunciado** detecta automaticamente o IP da VPN
3. No campo **IPs de peers**, digite o IP de pelo menos um amigo na VPN (ex: `25.10.10.5, 25.10.10.8`)
4. Entre na sala — os peers conectados irão propagar o anúncio para outros

## Configuração

Edite `app/config.py` para ajustar:

| Constante | Padrão | Descrição |
|---|---|---|
| `DEFAULT_FPS` | `15` | Frames por segundo do stream |
| `DEFAULT_JPEG_QUALITY` | `60` | Qualidade JPEG (1-95) |
| `DEFAULT_MAX_WIDTH` | `1280` | Resolução máxima (downscale automático) |
| `GRID_COLUMNS` | `2` | Colunas no grid de telas da sala |
| `DISCOVERY_PORT` | `47001` | Porta UDP para descoberta de peers |
| `BROADCAST_INTERVAL_S` | `1.5` | Intervalo entre anúncios de presença (segundos) |
| `PEER_TIMEOUT_S` | `5.0` | Tempo sem anúncio até considerar peer offline (segundos) |

## Auto-update (Windows frozen)

O programa verifica automaticamente novas versões via GitHub Releases:

- **Verificação automática:** 1 vez por dia ao iniciar (verifica `last_check` em estado persistente)
- **Verificação manual:** botão "🔄 Verificar Atualizações" na janela da sala
- **Integridade:** download verificado por SHA-256 obrigatório (arquivo `.exe.sha256` na release)
- **Persistência:** estado salvo em `%APPDATA%/MiniPresidente` (dev) ou pasta do exe (frozen)
- **Ignorar versão:** opção "Nunca mais" no dialog — a versão fica registrada e não é reapresentada
- **Modo dev:** auto-update é desabilitado silenciosamente (sem frozen)
- **Sem internet/releases:** se a API retorna 404, o update é pulado — isso é o comportamento esperado

### Criando a primeira release

1. Atualize `__version__` em `app/config.py` — o `pyproject.toml` lê esse valor dinamicamente
2. Crie a tag: `git tag v0.2.0 && git push origin v0.2.0`
3. Compile o exe: `pyinstaller MiniPresidente.spec`
4. Gere o hash: `certutil -hashfile dist/MiniPresidente.exe SHA256 > dist/MiniPresidente.exe.sha256`
5. Crie a release no GitHub e anexe `MiniPresidente.exe` e `MiniPresidente.exe.sha256` como assets

> **Nota:** sem uma release publicada, `releases/latest` retorna 404 e o update é pulado automaticamente.

## Estrutura do projeto

```
app/
  config.py           # constantes, __version__, configurações
  discovery.py         # descoberta de peers (broadcast + unicast/gossip)
  capture.py           # captura de tela + encode JPEG (mss + Pillow, thread-local)
  stream_server.py     # servidor TCP — frame compartilhado para todos os viewers
  stream_client.py     # cliente TCP — recebe frames de um transmissor
  self_preview.py      # preview local da tela sendo transmitida
  updater.py           # lógica de auto-update (fetch, download, verify, install)
  update_state.py      # estado persistente do auto-update (JSON)
  ui/
    lobby_window.py    # tela inicial (nome, sala, IP, seed peers)
    room_window.py     # sala: grid de telas + membros + botão transmitir/atualizar
    update_dialog.py   # dialog modal de atualização com download
  main.py              # ponto de entrada + UpdateController
tests/
  test_discovery.py    # testes de parse de seeds, validação de peers, IP
  test_stream_framing.py  # testes do protocolo de framing TCP
  test_update.py       # testes de versão, estado, hash, parsing de release
```

## Dependências

- [PySide6](https://doc.qt.io/qtforpython-6/) — interface gráfica (Qt)
- [mss](https://python-mss.readthedocs.io/) — captura de tela multi-plataforma
- [Pillow](https://pillow.readthedocs.io/) — compressão JPEG
- [packaging](https://packaging.pypa.io/) — comparação de versões semânticas

## Limitações conhecidas

- **Sem áudio** — apenas vídeo por enquanto
- **Um monitor por vez** — transmite o monitor principal (índice 1)
- **Sem lista de salas** — é necessário saber o nome da sala para entrar
- **Sem criptografia** — rede de confiança (pode adicionar TLS depois)
- **Sem SFU** — cada viewer conecta direto no transmissor (upload é o gargalo com muitos viewers)
- **VPN requer seed peer** — o broadcast automático não funciona em Radmin/Hamachi; é necessário informar pelo menos um IP de peer na lobby

## Licença

[MIT License](LICENSE)
