import subprocess
import logging
import threading
import socket
import struct
import os
import secrets
import time

logger = logging.getLogger(__name__)

# --- Estado Global ---
_server_process = None
_rcon_password = None
_rcon_port = 25575


# =============================================
# PROTOCOLO RCON (Source Engine / Minecraft)
# Implementação pura em Python, sem dependências.
# =============================================

def _rcon_criar_pacote(request_id, tipo, payload):
    """
    Monta um pacote RCON binário conforme a especificação:
    [4 bytes: tamanho] [4 bytes: request_id] [4 bytes: tipo] [payload + \x00] [\x00]
    """
    payload_bytes = payload.encode("utf-8") + b"\x00"  # null-terminated string
    padding = b"\x00"  # padding byte obrigatório
    corpo = struct.pack("<ii", request_id, tipo) + payload_bytes + padding
    return struct.pack("<i", len(corpo)) + corpo


def _rcon_ler_resposta(sock):
    """
    Lê exatamente um pacote de resposta RCON do socket.
    Retorna (request_id, tipo, payload_texto).
    """
    # Lê os 4 bytes do tamanho
    dados_tam = b""
    while len(dados_tam) < 4:
        pedaco = sock.recv(4 - len(dados_tam))
        if not pedaco:
            raise ConnectionError("Conexão RCON fechou inesperadamente ao ler tamanho.")
        dados_tam += pedaco

    tamanho = struct.unpack("<i", dados_tam)[0]

    # Lê o corpo completo
    dados_corpo = b""
    while len(dados_corpo) < tamanho:
        pedaco = sock.recv(tamanho - len(dados_corpo))
        if not pedaco:
            raise ConnectionError("Conexão RCON fechou inesperadamente ao ler corpo.")
        dados_corpo += pedaco

    request_id = struct.unpack("<i", dados_corpo[0:4])[0]
    tipo = struct.unpack("<i", dados_corpo[4:8])[0]
    payload = dados_corpo[8:-2].decode("utf-8", errors="replace")  # remove os 2 null bytes finais

    return request_id, tipo, payload


def _rcon_enviar_comando(host, porta, senha, comando):
    """
    Conecta ao RCON, autentica, envia um comando e retorna a resposta.
    Levanta exceção em caso de falha.
    """
    RCON_LOGIN = 3
    RCON_COMMAND = 2

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)  # 10 segundos para cada operação de rede

    try:
        sock.connect((host, porta))

        # 1. Login
        sock.sendall(_rcon_criar_pacote(1, RCON_LOGIN, senha))
        req_id, _, _ = _rcon_ler_resposta(sock)
        if req_id == -1:
            raise PermissionError("Senha RCON recusada pelo servidor Minecraft.")

        # 2. Enviar comando
        sock.sendall(_rcon_criar_pacote(2, RCON_COMMAND, comando))
        _, _, resposta = _rcon_ler_resposta(sock)
        return resposta

    finally:
        sock.close()


# =============================================
# PREPARAÇÃO AUTOMÁTICA DO server.properties
# =============================================

def _preparar_rcon_no_properties(server_dir):
    """
    Garante que o server.properties tenha o RCON ativado com senha segura.
    Gera uma senha aleatória a cada inicialização para máxima segurança.
    Retorna a senha gerada.
    """
    global _rcon_password, _rcon_port

    caminho = os.path.join(server_dir, "server.properties")
    senha = secrets.token_hex(16)  # 32 caracteres hexadecimais, impossível de adivinhar

    # Valores que queremos forçar
    rcon_configs = {
        "enable-rcon": "true",
        "rcon.password": senha,
        "rcon.port": str(_rcon_port),
    }

    if os.path.exists(caminho):
        with open(caminho, "r", encoding="utf-8") as f:
            linhas = f.readlines()

        chaves_encontradas = set()
        novas_linhas = []

        for linha in linhas:
            if "=" in linha and not linha.strip().startswith("#"):
                chave = linha.split("=", 1)[0].strip()
                if chave in rcon_configs:
                    novas_linhas.append(f"{chave}={rcon_configs[chave]}\n")
                    chaves_encontradas.add(chave)
                    continue
            novas_linhas.append(linha)

        # Adiciona as chaves que não existiam no arquivo
        for chave, valor in rcon_configs.items():
            if chave not in chaves_encontradas:
                novas_linhas.append(f"{chave}={valor}\n")

        with open(caminho, "w", encoding="utf-8") as f:
            f.writelines(novas_linhas)
    else:
        # Se o arquivo não existe, cria com o mínimo necessário
        with open(caminho, "w", encoding="utf-8") as f:
            for chave, valor in rcon_configs.items():
                f.write(f"{chave}={valor}\n")

    _rcon_password = senha
    logger.info(f"RCON configurado automaticamente na porta {_rcon_port}.")
    return senha


# =============================================
# EXECUÇÃO DO SERVIDOR MINECRAFT
# =============================================

def _esvaziar_tubo(processo):
    """Lê continuamente a saída do Java para evitar o entupimento do PIPE (Deadlock)."""
    try:
        for linha in iter(processo.stdout.readline, ''):
            if not linha:
                break
    except Exception:
        pass


def run_minecraft_server(java_exe, server_dir, jar_name):
    """
    Inicia o servidor Minecraft como processo invisível.
    Configura o RCON automaticamente antes de iniciar.
    Bloqueia a thread até o processo Java morrer.
    """
    global _server_process

    # Prepara o RCON antes de lançar o servidor
    _preparar_rcon_no_properties(server_dir)

    comando = [
        java_exe,
        "-Xmx4G",
        "-Xms1G",
        "-jar",
        jar_name,
        "nogui"
    ]

    logger.info("Iniciando o processo do Minecraft (RCON Ativado)...")

    # Usa STARTUPINFO para ocultar a janela do Java no Windows
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE

    _server_process = subprocess.Popen(
        comando,
        cwd=server_dir,
        startupinfo=startupinfo,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Thread "ralo" para drenar a saída e evitar deadlock de buffer
    thread_leitora = threading.Thread(target=_esvaziar_tubo, args=(_server_process,), daemon=True)
    thread_leitora.start()

    # Congela a thread aqui até o processo do Java morrer
    _server_process.wait()
    logger.info(f"Processo do Minecraft encerrado. Código de saída: {_server_process.returncode}")
    _server_process = None


def stop_minecraft_server():
    """
    Para o servidor de forma limpa usando RCON.
    
    Estratégia em 3 camadas:
    1. Tenta enviar 'stop' via RCON (mais confiável)
    2. Se RCON falhar, tenta via stdin como fallback
    3. Se nada funcionar em 30s, mata o processo à força
    """
    global _server_process

    if not _server_process or _server_process.poll() is not None:
        logger.warning("Tentativa de parar o servidor, mas ele já estava morto.")
        return

    # --- CAMADA 1: RCON ---
    rcon_ok = False
    if _rcon_password:
        logger.info(f"Enviando 'stop' via RCON (porta {_rcon_port})...")
        for tentativa in range(3):
            try:
                _rcon_enviar_comando("127.0.0.1", _rcon_port, _rcon_password, "stop")
                logger.info("Comando 'stop' enviado via RCON com sucesso!")
                rcon_ok = True
                break
            except ConnectionRefusedError:
                logger.warning(f"RCON recusou conexão (tentativa {tentativa + 1}/3). Aguardando...")
                time.sleep(2)
            except Exception as e:
                logger.warning(f"Falha no RCON (tentativa {tentativa + 1}/3): {e}")
                time.sleep(2)

    # --- CAMADA 2: Stdin (fallback) ---
    if not rcon_ok:
        logger.info("RCON falhou. Tentando fallback via stdin...")
        try:
            if _server_process and _server_process.poll() is None:
                _server_process.stdin.write("stop\n")
                _server_process.stdin.flush()
        except Exception as e:
            logger.error(f"Fallback stdin também falhou: {e}")

    # --- CAMADA 3: Timeout + Kill ---
    # Aguarda até 30 segundos pelo shutdown gracioso
    def _vigilante_timeout():
        try:
            _server_process.wait(timeout=30)
            logger.info("Servidor encerrou dentro do prazo de 30 segundos.")
        except Exception:
            logger.warning("TIMEOUT! Servidor não morreu em 30s. Forçando encerramento...")
            try:
                _server_process.terminate()
                _server_process.wait(timeout=10)
            except Exception:
                logger.error("terminate() falhou. Usando kill() como último recurso.")
                try:
                    _server_process.kill()
                except Exception:
                    pass

    threading.Thread(target=_vigilante_timeout, daemon=True).start()