import time
import logging
import requests
import sys
import os
import threading
from dotenv import load_dotenv

# Atualiza o sys.path para achar os outros scripts em qualquer PC
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    CURRENT_DIR = BASE_DIR
else:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(CURRENT_DIR)

sys.path.append(os.path.join(BASE_DIR, "ambiente_teste"))
sys.path.append(CURRENT_DIR)

DOTENV_PATH = os.path.join(BASE_DIR, "config", ".env")
load_dotenv(dotenv_path=DOTENV_PATH)

try:
    from firebase_lock import get_cluster_state, acquire_lock
    from rclone_sync import rclone_pull, rclone_push
    from network_routing import tailscale_up, tailscale_down, get_tailscale_ip, update_duckdns
    from server_executor import run_minecraft_server, stop_minecraft_server
    from gestor_banco import alternar_fila, obter_dados_cluster, obter_chaves_servidor
except ImportError as e:
    print(f"Erro crítico de montagem (ImportError): {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configurações / Variáveis de Ambiente ---
AUTH_TOKEN = os.getenv("AUTH_TOKEN")
MY_ID_IP = "local-host-node"

# Filtro Triturador: Limpa qualquer lixo de URL
DB_URL_RAW = os.getenv("DB_URL")
DB_URL_BASE = DB_URL_RAW.split("/estado_cluster")[0].split("/cluster")[0].replace(".json", "").strip("/")
DB_URL = f"{DB_URL_BASE}/.json"

# Monta os caminhos dos executáveis e pastas dinamicamente
RCLONE_EXE = os.path.join(BASE_DIR, "dependencias", "rclone.exe")
LOCAL_DIR = os.path.join(BASE_DIR, "ambiente_teste", "world")
JAVA_EXE = os.path.join(BASE_DIR, "dependencias", "jre", "bin", "java.exe")
SERVER_DIR = os.path.join(BASE_DIR, "ambiente_teste")
JAR_NAME = "server.jar"

GHOST_DOWNLOAD_INTERVAL = 10 * 60  # 10 minutos
_ghost_ativo = False

def preparar_rclone_conf(conteudo_token, codigo_servidor):
    """Gera um arquivo rclone.conf temporário e injeta o token do criador do servidor"""
    caminho_conf = os.path.join(BASE_DIR, "config", f"rclone_{codigo_servidor}.conf")
    
    with open(caminho_conf, "w", encoding="utf-8") as f:
        # Se colou só o JSON do token, monta a casca do Drive em volta
        if conteudo_token.strip().startswith("{"):
            f.write("[gdrive]\n")
            f.write("type = drive\n")
            f.write("scope = drive\n")
            f.write(f"token = {conteudo_token}\n")
        else:
            # Se colou o arquivo conf inteiro, salva direto
            f.write(conteudo_token)
            
    return caminho_conf

def _loop_ghost_download(callback_status, rclone_conf_path, codigo_servidor):
    """Thread que atualiza o mapa silenciosamente a cada 10 minutos"""
    global _ghost_ativo
    # Agora o caminho é único para cada servidor
    remote_dir_dinamico = f"gdrive:Minecraft/Servidores/{codigo_servidor}/world"
    
    while _ghost_ativo:
        time.sleep(GHOST_DOWNLOAD_INTERVAL)
        if _ghost_ativo:
            if callback_status: callback_status("Ghost Download: Sincronizando mapa em background...", "blue")
            try:
                rclone_pull(RCLONE_EXE, rclone_conf_path, remote_dir_dinamico, LOCAL_DIR, blocking=True)
            except Exception as e:
                logger.error(f"Erro no Ghost Download: {e}")
            if _ghost_ativo and callback_status: 
                callback_status("Ghost Download concluído. Aguardando servidor...", "blue")

def release_firebase_lock(codigo_servidor):
    """Função atômica para devolver a liderança ao ecossistema."""
    url_cluster = f"{DB_URL_BASE}/servidores/{codigo_servidor}/cluster.json"
    logger.info("Liberando o Lock no Firebase (Mudando status para OFFLINE)...")
    estado_livre = {
        "status": "OFFLINE",
        "host_ativo_ip": None,
        "timestamp_ultimo_save": int(time.time())
    }
    try:
        requests.put(url_cluster, params={'auth': AUTH_TOKEN}, json=estado_livre, timeout=5.0)
        logger.info("O nó declinou a liderança com sucesso.")
    except Exception as e:
        logger.error(f"Falha de rede ao tentar soltar o Mutex: {e}")

def sair_do_relay(nome_usuario, codigo_servidor):
    """Chamada quando o utilizador desiste da fila ou fecha o programa (Corta o sanguessuga)"""
    global _ghost_ativo
    _ghost_ativo = False
    logger.info("Saindo do Relay. Removendo da fila e cortando VPN...")
    alternar_fila(DB_URL, AUTH_TOKEN, codigo_servidor, nome_usuario, entrar=False)
    tailscale_down()

def executar_ciclo_host(nome_usuario, codigo_servidor, callback_status=None):
    def log_ui(mensagem, cor="gray"):
        logger.info(mensagem)
        if callback_status: callback_status(mensagem, cor)

    global _ghost_ativo
    lock_adquirido = False 
    url_cluster = f"{DB_URL_BASE}/servidores/{codigo_servidor}/cluster.json"
    # Caminho organizado por servidor
    remote_dir_dinamico = f"gdrive:Minecraft/Servidores/{codigo_servidor}/world"

    try:
        log_ui("Obtendo chaves de segurança do servidor...", "orange")
        chaves = obter_chaves_servidor(DB_URL, AUTH_TOKEN, codigo_servidor)
        ts_key = chaves.get("tailscale_key")
        duck_domain = chaves.get("duckdns_domain")
        duck_token = chaves.get("duckdns_token")
        rclone_token = chaves.get("rclone_token")

        if not ts_key or not rclone_token:
            log_ui("Falha: Chaves essenciais (VPN/Drive) não encontradas.", "red")
            time.sleep(4)
            return

        rclone_conf_path = preparar_rclone_conf(rclone_token, codigo_servidor)

        # 1. O PEDÁGIO: Liga a VPN
        log_ui("Pagando pedágio: Conectando VPN (Tailscale)...", "orange")
        tailscale_up(ts_key)
        
        log_ui("Verificando cluster e Fila de Espera...", "orange")
        estado_cluster, etag = get_cluster_state(url_cluster, AUTH_TOKEN)
        
        if estado_cluster is None:
            log_ui("Falha: Nó /cluster não encontrado ou erro de ETag.", "red")
            time.sleep(4)
            return

        # =========================================================
        # MODO CLIENTE (ENTRAR NA FILA E ACIONAR GHOST DOWNLOAD)
        # =========================================================
        if estado_cluster.get("status") == "ONLINE":
            log_ui("Servidor em uso! Colocando você na fila de espera...", "blue")
            alternar_fila(DB_URL, AUTH_TOKEN, codigo_servidor, nome_usuario, entrar=True)
            
            if not _ghost_ativo:
                _ghost_ativo = True
                threading.Thread(target=_loop_ghost_download, args=(callback_status, rclone_conf_path, codigo_servidor), daemon=True).start()
            
            time.sleep(3)
            return 

        # Verifica a Fila antes de assumir
        dados_completos = obter_dados_cluster(DB_URL, AUTH_TOKEN, codigo_servidor)
        fila = dados_completos.get("fila", [])
        
        if fila and fila[0] != nome_usuario:
            log_ui(f"O próximo é {fila[0]}. Entrando na fila...", "blue")
            alternar_fila(DB_URL, AUTH_TOKEN, codigo_servidor, nome_usuario, entrar=True)
            if not _ghost_ativo:
                _ghost_ativo = True
                threading.Thread(target=_loop_ghost_download, args=(callback_status, rclone_conf_path, codigo_servidor), daemon=True).start()
            time.sleep(3)
            return

        # =========================================================
        # MODO HOST (ASSUMIR O BASTÃO DO SERVIDOR)
        # =========================================================
        if not acquire_lock(url_cluster, AUTH_TOKEN, nome_usuario, etag):
            log_ui("Falha: Outro jogador pegou a vaga no mesmo milissegundo.", "red")
            time.sleep(4)
            return

        lock_adquirido = True 
        _ghost_ativo = False 
        
        alternar_fila(DB_URL, AUTH_TOKEN, codigo_servidor, nome_usuario, entrar=False)

        log_ui("Transferindo mapa atualizado (Rclone)...", "orange")
        rclone_pull(RCLONE_EXE, rclone_conf_path, remote_dir_dinamico, LOCAL_DIR, blocking=True)

        ip_virtual = get_tailscale_ip()
        if ip_virtual and duck_domain and duck_token:
            log_ui(f"Roteando DNS para {ip_virtual}...", "orange")
            update_duckdns(duck_domain, duck_token, ip_virtual)

        log_ui("ONLINE! Feche a janela do jogo para passar o bastão.", "green")
        run_minecraft_server(JAVA_EXE, SERVER_DIR, JAR_NAME)

        log_ui("Server fechado. Salvando mapa na nuvem...", "orange")
        time.sleep(5)
        rclone_push(RCLONE_EXE, rclone_conf_path, LOCAL_DIR, remote_dir_dinamico)

    except Exception as e:
        logger.error(f"Erro Crítico no ciclo: {e}")
        log_ui(f"Erro Interno: {e}", "red")
        time.sleep(5)
        
    finally:
        if lock_adquirido:
            log_ui("Desmontando VPN e liberando bastão para o próximo...", "orange")
            tailscale_down()
            release_firebase_lock(codigo_servidor)
            log_ui("Standby", "gray")

def encerrar_host_local():
    """Função exportada para o Launcher acionar o Teardown de forma segura."""
    logger.info("Recebido sinal da Interface para encerrar o servidor.")
    stop_minecraft_server()

def deletar_mundo_local():
    """Apaga a pasta 'world' local para forçar um download limpo."""
    import shutil
    caminho_mundo = os.path.join(SERVER_DIR, "world")
    if os.path.exists(caminho_mundo):
        shutil.rmtree(caminho_mundo)
        logger.info("Pasta 'world' deletada com sucesso.")
        return True
    return False

def sincronizacao_manual(codigo_servidor, modo="pull_world", callback_status=None):
    """Permite ao Launcher forçar downloads ou uploads manuais sem iniciar o Minecraft"""
    def log_ui(msg, cor="gray"):
        logger.info(msg)
        if callback_status: callback_status(msg, cor)

    try:
        log_ui("Autenticando na nuvem...", "orange")
        chaves = obter_chaves_servidor(DB_URL, AUTH_TOKEN, codigo_servidor)
        rclone_token = chaves.get("rclone_token")

        if not rclone_token:
            log_ui("Falha: Token do Drive não encontrado.", "red")
            return

        rclone_conf_path = preparar_rclone_conf(rclone_token, codigo_servidor)
        
        if modo == "pull_world":
            log_ui("Baixando mapa atualizado da nuvem...", "blue")
            remote_dir = f"gdrive:Minecraft/Servidores/{codigo_servidor}/world"
            rclone_pull(RCLONE_EXE, rclone_conf_path, remote_dir, LOCAL_DIR, blocking=True)
            log_ui("Download concluído com sucesso!", "green")
            
        elif modo == "push_admin":
            log_ui("[ADMIN] Enviando mods/plugins e mapa para a nuvem...", "blue")
            # Agora salva a raiz do servidor dentro da pasta dele, e não na raiz do Minecraft
            remote_dir_admin = f"gdrive:Minecraft/Servidores/{codigo_servidor}"
            import time
            time.sleep(5)
            rclone_push(RCLONE_EXE, rclone_conf_path, SERVER_DIR, remote_dir_admin)
            log_ui("Upload Master concluído! Todos os membros receberão as alterações.", "green")

    except Exception as e:
        log_ui(f"Erro na sincronização: {e}", "red")