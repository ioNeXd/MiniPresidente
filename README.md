# MiniPresidente

Compartilhamento de tela peer-to-peer para redes locais (LAN) ou VPNs. Qualquer pessoa na mesma rede cria ou entra numa sala e transmite sua tela ao mesmo tempo — como o Discord, mas sem servidor central.

## Funcionalidades

- **Descoberta automática de peers** via broadcast UDP — quem entra na mesma sala aparece automaticamente
- **Transmissão de tela em tempo real** — JPEG sobre TCP, com captura via `mss` (funciona em Windows, Linux e Mac)
- **Grid de telas lado a lado** — assista as telas de todos os membros da sala ao mesmo tempo
- **Preview local** — veja sua própria tela sendo transmitida
- **Suporte a VPN** — detecção automática de IP de VPN (Radmin, Hamachi, etc.) com override manual na tela inicial
- **Interface gráfica** — lobby para entrar na sala + janela da sala com grid de telas e lista de membros
- **Empacotamento** — pode ser distribuído como executável standalone via PyInstaller

## Como instalar (terminal)

Precisa de **Python 3.10+**.

```bash
# Clonar o repositório
git clone https://github.com/SEU_USUARIO/minipresidente.git
cd minipresidente

# Criar e ativar ambiente virtual
python -m venv venv

# Windows:
venv\Scripts\activate

# Linux / Mac:
source venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Rodar o programa
python -m app.main
```

Cada amigo roda o mesmo comando na própria máquina. Digite o mesmo **nome de sala** pra todo mundo cair junto.

## Executável (.exe)

Para quem não tem Python instalado, é possível gerar um executável standalone:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name="MiniPresidente" --hidden-import=PySide6.QtSvg app/main.py
```

O executável gerado fica em `dist/MiniPresidente.exe`. Distribua apenas esse arquivo — não precisa de Python nem de pastas adicionais.

## Uso com VPN (Radmin / Hamachi)

1. Instale a VPN e conecte-se à rede dos amigos
2. Abra o programa — o campo **IP anunciado** na tela inicial detecta automaticamente o IP da VPN
3. Verifique se o IP está correto (deve ser o da VPN, ex: `25.x.x.x`), senão edite manualmente
4. Entre na sala normalmente

O programa prioriza IPs que **não** são da LAN física (192.168.x, 10.x, 172.16-31.x), assumindo que esses são IPs de VPN.

## Configuração

Edite `app/config.py` para ajustar:

| Constante | Padrão | Descrição |
|---|---|---|
| `DEFAULT_FPS` | `15` | Frames por segundo do stream (mais = mais CPU e banda) |
| `DEFAULT_JPEG_QUALITY` | `60` | Qualidade JPEG (1-95, mais alto = melhor imagem) |
| `DEFAULT_MAX_WIDTH` | `1280` | Resolução máxima (downscale automático) |
| `GRID_COLUMNS` | `2` | Colunas no grid de telas da sala |
| `DISCOVERY_PORT` | `47001` | Porta UDP de broadcast para descoberta de peers |

## Estrutura do projeto

```
app/
  config.py           # constantes e configurações
  discovery.py         # descoberta de peers via broadcast UDP
  capture.py           # captura de tela + encode JPEG (mss + Pillow)
  stream_server.py     # servidor TCP — envia frames para quem assistir
  stream_client.py     # cliente TCP — recebe frames de um transmissor
  self_preview.py      # preview local da tela sendo transmitida
  ui/
    lobby_window.py    # tela inicial (nome, sala, IP)
    room_window.py     # sala: grid de telas + membros + botão transmitir
  main.py              # ponto de entrada
```

## Dependências

- [PySide6](https://doc.qt.io/qtforpython-6/) — interface gráfica (Qt)
- [mss](https://python-mss.readthedocs.io/) — captura de tela multi-plataforma
- [Pillow](https://pillow.readthedocs.io/) — compressão JPEG

## Licença

Este projeto está licenciado sob a [MIT License](LICENSE).

## Limitações conhecidas

- **Sem áudio** — apenas vídeo por enquanto
- **Um monitor por vez** — transmite o monitor principal (índice 1)
- **Sem lista de salas** — é necessário saber o nome da sala para entrar
- **Sem criptografia** — rede LAN de confiança (pode adicionar TLS depois)
- **Sem SFU** — cada viewer conecta direto no transmissor (upload do transmissor é o gargalo com muitos viewers)
