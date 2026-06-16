import os
import subprocess
import logging
from typing import Optional

# Configuração básica do logger para registrar as operações
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flag para suprimir a criação de janela do terminal no ambiente Windows
# É equivalente ao STARTF_USESHOWWINDOW, mas mais direto nas versões recentes do Python
CREATE_NO_WINDOW = 0x08000000

def _get_subprocess_kwargs() -> dict:
    """
    Função utilitária para injetar os argumentos necessários (kwargs) 
    para o subprocess não criar nenhuma janela (console prompt) durante a execução.
    
    Returns:
        dict: Dicionário contendo a configuração de criação de processo sem janela, 
              apenas se o sistema operacional for Windows (NT).
    """
    kwargs = {}
    if os.name == 'nt':
        # Como o processo é de fato invisível, garantimos que não haja pop-ups do cmd.exe
        kwargs['creationflags'] = CREATE_NO_WINDOW
    return kwargs

def rclone_pull(rclone_exe: str, config_path: str, remote_dir: str, local_dir: str, blocking: bool = False) -> Optional[subprocess.Popen]:
    """
    Executa o download dos dados da nuvem para o disco local (P2P Delta-Sync).
    
    Args:
        rclone_exe (str): Caminho absoluto para o 'rclone.exe'.
        config_path (str): Caminho absoluto para o arquivo 'rclone.conf'.
        remote_dir (str): Diretório remoto origem (ex: 'gdrive:Minecraft/World').
        local_dir (str): Diretório local destino.
        blocking (bool): Se 'True', aguarda o fim do download (subprocess.run). 
                         Se 'False', cria um 'Ghost Download' (subprocess.Popen) e retorna o processo.
        
    Returns:
        Optional[subprocess.Popen]: Retorna a instância do processo Popen se non-blocking, 
                                    ou None se for bloqueante ou ocorrer erro.
    """
    cmd = [
        rclone_exe,
        "sync",  # Compara e sincroniza estritamente os arquivos
        remote_dir,
        local_dir,
        "--config", config_path,
        "--update",      # Delta-sync: pula arquivos que já são mais novos no destino
        "--transfers", "16",
        "--checkers", "16",
        "--drive-chunk-size", "64M",
        "--fast-list",  # Otimização de I/O em checagens concorrentes
        "--verbose" 
    ]
    
    kwargs = _get_subprocess_kwargs()
    
    try:
        if blocking:
            logger.info("Iniciando 'rclone_pull' bloqueante...")
            subprocess.run(cmd, check=True, **kwargs)
            logger.info("Download bloqueante finalizado.")
            return None
        else:
            logger.info("Iniciando 'rclone_pull' em background (Ghost Download)...")
            # Inicia o processo de forma desanexada e não trava a thread principal
            process = subprocess.Popen(cmd, **kwargs)
            return process
            
    except FileNotFoundError:
        logger.error(f"Crítico: 'rclone.exe' não encontrado no caminho fornecido: {rclone_exe}")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Falha na execução do Rclone Pull (Erro no Subprocesso): {e}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado (Pull): {e}")
        return None

def rclone_push(rclone_exe: str, config_path: str, local_dir: str, remote_dir: str) -> bool:
    """
    Executa o upload dos dados salvos no disco local para a nuvem.
    Esta operação é projetada para ser bloqueante, garantindo que o Mutex (Firebase)
    não seja liberado antes da conclusão total e íntegra do upload.
    
    Args:
        rclone_exe (str): Caminho absoluto para o 'rclone.exe'.
        config_path (str): Caminho absoluto para o arquivo 'rclone.conf'.
        local_dir (str): Diretório local origem.
        remote_dir (str): Diretório remoto destino (ex: 'gdrive:Minecraft/World').
        
    Returns:
        bool: True se a operação sincronizou os dados com sucesso para a nuvem, False em caso de erro.
    """
    cmd = [
        rclone_exe,
        "sync", 
        local_dir,
        remote_dir,
        "--config", config_path,
        "--update",      # Delta-sync garante que só os blocos do mapa (.mca) atualizados subam
        "--transfers", "16",
        "--checkers", "16",
        "--drive-chunk-size", "64M",
        "--fast-list",
        "--verbose"
    ]
    
    kwargs = _get_subprocess_kwargs()
    
    try:
        logger.info("Iniciando 'rclone_push' (Upload Bloqueante)...")
        # O subprocess.run por si só já bloqueia a thread, aguardando o processo terminar.
        # check=True fará com que lances de erros do rclone ativem o CalledProcessError.
        subprocess.run(cmd, check=True, **kwargs)
        logger.info("Upload finalizado e validado no Rclone.")
        return True
        
    except FileNotFoundError:
        logger.error(f"Crítico: 'rclone.exe' não encontrado no caminho: {rclone_exe}")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Falha de sincronização (Push). Processo rclone retornou um erro: {e}")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado (Push): {e}")
        return False
