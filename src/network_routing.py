import os
import subprocess
import logging
import requests
from typing import Optional

# Configuração básica de logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constante para ocultar a janela de prompt de comando no Windows
CREATE_NO_WINDOW = 0x08000000

def _get_subprocess_kwargs() -> dict:
    """
    Retorna os argumentos kwargs necessários para que a execução do subprocesso
    ocorra silenciosamente (sem abrir tela de console) em ambiente Windows.
    """
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = CREATE_NO_WINDOW
    return kwargs

def tailscale_up(auth_key: str) -> bool:
    """Sobe a VPN e lida com chaves expiradas/inválidas"""
    cmd = [r"C:\Program Files\Tailscale\tailscale.exe", "up", f"--authkey={auth_key}", "--reset"]
    kwargs = _get_subprocess_kwargs()
    
    try:
        logger.info("Iniciando conexão com a rede Tailscale...")
        # O terminal fica oculto e capturamos tudo para ver se a chave expirou
        processo = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
        
        saida_erro = processo.stderr.lower() if processo.stderr else ""
        saida_normal = processo.stdout.lower() if processo.stdout else ""
        
        # Caçando o erro letal do Tailscale
        if "expired" in saida_erro or "invalid authkey" in saida_erro or "expired" in saida_normal:
            raise ValueError("ERRO_TS_EXPIRADA")
            
        if processo.returncode != 0:
            raise Exception(f"Falha ao ligar VPN: {processo.stderr}")
            
        logger.info("Conexão com Tailscale estabelecida com sucesso.")
        return True
        
    except FileNotFoundError:
        logger.error("Erro: 'tailscale' não encontrado no PATH do sistema.")
        return False
    except ValueError as e:
        # Repassa o erro específico de expiração para a mente_coletiva.py
        raise e
    except Exception as e:
        logger.error(f"Erro inesperado em tailscale_up: {e}")
        return False

def tailscale_down() -> bool:
    """
    Desconecta a máquina da rede Tailscale. Útil para limpar o estado quando 
    este nó perde ou abdica da posição de líder.
    
    Returns:
        bool: True se o processo retornou código de saída 0 (sucesso), False caso contrário.
    """
    cmd = [r"C:\Program Files\Tailscale\tailscale.exe", "down"]
    kwargs = _get_subprocess_kwargs()
    
    try:
        logger.info("Encerrando conexão com a rede Tailscale...")
        subprocess.run(cmd, check=True, **kwargs)
        logger.info("Desconectado do Tailscale com sucesso.")
        return True
    except FileNotFoundError:
        logger.error("Erro: 'tailscale' não encontrado no PATH do sistema.")
        return False
    except subprocess.CalledProcessError as e:
        logger.error(f"Falha ao executar 'tailscale down'. Código de erro: {e.returncode}")
        return False
    except Exception as e:
        logger.error(f"Erro inesperado em tailscale_down: {e}")
        return False

def get_tailscale_ip() -> Optional[str]:
    """
    Obtém o endereço IPv4 atual da máquina na rede Tailscale overlay.
    
    Returns:
        Optional[str]: O IP da máquina em formato texto, ou None se ocorrer erro 
                       ou nenhum IP for retornado.
    """
    cmd = [r"C:\Program Files\Tailscale\tailscale.exe", "ip", "-4"]
    kwargs = _get_subprocess_kwargs()
    
    try:
        logger.info("Consultando IP da overlay network do Tailscale...")
        # capture_output e text=True permitem capturar a resposta para uma string em vez de imprimir na tela
        result = subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)
        ip = result.stdout.strip()
        
        if ip:
            logger.info(f"IP do Tailscale obtido: {ip}")
            return ip
        else:
            logger.warning("Comando executou com sucesso, mas o Tailscale não retornou um IP.")
            return None
            
    except FileNotFoundError:
        logger.error("Erro: 'tailscale' não encontrado no PATH do sistema.")
        return None
    except subprocess.CalledProcessError as e:
        logger.error(f"Falha ao obter IP do Tailscale (Código {e.returncode}). Saída: {e.stderr.strip()}")
        return None
    except Exception as e:
        logger.error(f"Erro inesperado em get_tailscale_ip: {e}")
        return None

def update_duckdns(domain: str, token: str, ip: str) -> bool:
    """
    Atualiza o apontamento de DNS dinâmico do DuckDNS para o IP fornecido.
    A API deles é simples: GET request e retorna 'OK' para sucesso ou 'KO' para falha.
    
    Args:
        domain (str): O subdomínio registrado (ex: 'meu-cluster-mc').
        token (str): O token de API (UUID) providenciado pelo DuckDNS.
        ip (str): O novo endereço IP alvo (O IP do Tailscale que capturamos).
        
    Returns:
        bool: True se a resposta for 'OK', False se 'KO' ou erro de rede.
    """
    url = f"https://www.duckdns.org/update?domains={domain}&token={token}&ip={ip}"
    
    try:
        logger.info(f"Atualizando apontamento do DuckDNS [{domain}] para IP -> {ip}...")
        response = requests.get(url, timeout=10.0)
        response.raise_for_status()
        
        # Lê e higieniza a resposta da API (Plaintext OK ou KO)
        status_api = response.text.strip()
        
        if status_api == "OK":
            logger.info("Atualização DuckDNS validada (OK) com sucesso.")
            return True
        elif status_api == "KO":
            logger.error("A API do DuckDNS recusou a atualização (KO). O token ou domínio podem estar incorretos.")
            return False
        else:
            logger.warning(f"A API retornou uma resposta não mapeada: '{status_api}'")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro de comunicação/rede com a API do DuckDNS: {e}")
        return False
