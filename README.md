# MiniPresidente

Compartilhamento de tela peer-to-peer para redes locais (LAN) ou VPNs. Qualquer pessoa na mesma rede cria ou entra numa sala e transmite sua tela ao mesmo tempo — como o Discord, mas sem servidor central.

## Funcionalidades

- **Descoberta automática de peers** via broadcast UDP em LAN física
- **Descoberta via VPN** com unicast para seed peers + gossip automático
- **Transmissão de tela em tempo real** — vídeo codificado em **H.264** (via PyAV/libx264), captura via `mss` (Windows, Linux e Mac)
- **Qualidade configurável** — resolução (360p a 1440p ou resolução de origem), FPS (5/15/30/60/120) e bitrate de vídeo ajustáveis na lobby antes de entrar na sala
- **Grid de telas lado a lado** — assista as telas de todos os membros da sala
- **Preview local fiel** — veja sua própria tela sendo transmitida, no mesmo FPS e formato usados na transmissão real
- **Interface gráfica** — lobby + janela da sala com grid de telas e lista de membros
- **Empacotamento** — executável standalone via PyInstaller
- **Auto-update** — verificação automática de atualizações via GitHub Releases (Windows frozen)

## Como instalar (terminal)

Precisa de **Python 3.10+**. A codificação de vídeo usa [PyAV](https://pyav.org/), que já traz o FFmpeg/libx264 embutido no pacote — não é necessário instalar FFmpeg separadamente na maioria dos sistemas.

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

## Qualidade de vídeo

Antes de entrar na sala, a lobby permite ajustar:

| Opção | Valores | Padrão |
|---|---|---|
| Resolução | 360p / 480p / 720p / 1080p / 1440p / origem (resolução nativa do monitor) | 1080p |
| FPS | 5 / 15 / 30 / 60 / 120 | 30 |
| Bitrate de vídeo | varia por resolução (ex: 2500–12000 kbps em 1080p) | conforme preset da resolução |

Cada resolução tem uma faixa de bitrate mínima/máxima associada (ver `RESOLUTION_PRESETS` em `app/session_config.py`). A lobby avisa quando a combinação escolhida (ex: 1440p a 120 FPS) tende a ser pesada sem uma placa dedicada.

> **Nota:** a lobby também expõe um seletor de bitrate de áudio, mas **a captura/transmissão de áudio ainda não está implementada** — ver Limitações conhecidas.

## Configuração

Edite `app/config.py` para ajustar as constantes de base do sistema:

| Constante | Padrão | Descrição |
|---|---|---|
| `DEFAULT_MAX_WIDTH` | `1280` | Largura máxima usada como fallback (a resolução escolhida na lobby tem prioridade) |
| `MAX_FRAME_BYTES` | `32 MiB` | Limite do protocolo de framing TCP — rejeita payloads de vídeo absurdamente grandes |
| `GRID_COLUMNS` | `2` | Colunas no grid de telas da sala |
| `DISCOVERY_PORT` | `47001` | Porta UDP para descoberta de peers |
| `BROADCAST_INTERVAL_S` | `1.5` | Intervalo entre anúncios de presença (segundos) |
| `PEER_TIMEOUT_S` | `5.0` | Tempo sem anúncio até considerar peer offline (segundos) |

Resolução, FPS e bitrate de vídeo/áudio são configurados por sessão na lobby (ver `app/session_config.py`), não em `config.py`.

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
  config.py           # constantes globais, __version__, configurações fixas
  session_config.py    # config por sessão: resolução, FPS, bitrate, presets de qualidade
  discovery.py         # descoberta de peers (broadcast + unicast/gossip)
  capture.py           # captura de tela (mss + Pillow, thread-local); RGB cru p/ H.264
  video_codec.py       # encoder/decoder H.264 (PyAV/libx264)
  stream_server.py     # servidor TCP — encoda e distribui frames H.264 para todos os viewers
  stream_client.py     # cliente TCP — recebe e decodifica o stream H.264 de um transmissor
  self_preview.py       # preview local (RGB cru), no mesmo FPS/formato da transmissão real
  room_session.py      # orquestra discovery + transmissão + viewers de uma sala
  updater.py           # lógica de auto-update (fetch, download, verify, install)
  update_state.py       # estado persistente do auto-update (JSON)
  ui/
    lobby_window.py    # tela inicial (nome, sala, IP, seed peers, qualidade de vídeo)
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
- [PyAV](https://pyav.org/) — encoding/decoding de vídeo H.264 (bindings do FFmpeg/libx264)
- [mss](https://python-mss.readthedocs.io/) — captura de tela multi-plataforma
- [Pillow](https://pillow.readthedocs.io/) — redimensionamento de frame antes do encode
- [packaging](https://packaging.pypa.io/) — comparação de versões semânticas

## Limitações conhecidas

- **Sem áudio** — apenas vídeo por enquanto (o seletor de bitrate de áudio na lobby é reservado para uma implementação futura)
- **Um monitor por vez** — transmite o monitor principal (índice 1)
- **Sem lista de salas** — é necessário saber o nome da sala para entrar
- **Sem criptografia** — rede de confiança (pode adicionar TLS depois)
- **Sem SFU** — cada viewer conecta direto no transmissor (upload é o gargalo com muitos viewers)
- **VPN requer seed peer** — o broadcast automático não funciona em Radmin/Hamachi; é necessário informar pelo menos um IP de peer na lobby

## Licença

[MIT License](LICENSE)
