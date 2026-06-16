import time
import requests
from typing import Tuple, Optional, Dict, Any

def get_cluster_state(URL_CLUSTER: str, auth_token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Obtém o estado atual do cluster e o ETag correspondente no Firebase Realtime Database.
    
    Args:
        URL_CLUSTER (str): A URL do endpoint no banco de dados (ex: https://<project>.firebaseio.com/estado_cluster.json).
        auth_token (str): O token de autenticação (REST API key ou token de acesso).
        
    Returns:
        Tuple[Optional[Dict[str, Any]], Optional[str]]: Uma tupla contendo o estado do cluster (como um dicionário)
        e o ETag (como uma string). Retorna (None, None) em caso de falha de comunicação ou timeout.
    """
    # A documentação do Firebase exige o cabeçalho 'X-Firebase-ETag' como 'true' para retornar o ETag
    headers = {
        'X-Firebase-ETag': 'true'
    }
    params = {
        'auth': auth_token
    }
    
    try:
        response = requests.get(URL_CLUSTER, headers=headers, params=params, timeout=5.0)
        response.raise_for_status()
        
        estado = response.json()
        etag = response.headers.get('ETag')
        
        return estado, etag
        
    except requests.exceptions.Timeout:
        print("Erro: Tempo limite de requisição (Timeout) atingido ao buscar o estado do cluster.")
        return None, None
    except requests.exceptions.RequestException as e:
        print(f"Erro de rede ao buscar o estado do cluster: {e}")
        return None, None


def acquire_lock(URL_CLUSTER: str, auth_token: str, my_ip: str, current_etag: str) -> bool:
    """
    Tenta adquirir o lock de liderança (Leader Election) usando uma requisição condicional (ETag).
    Para evitar Condição de Corrida (Split-Brain), a atualização só é feita se o ETag bater.
    
    Args:
        URL_CLUSTER (str): A URL do endpoint no banco de dados.
        auth_token (str): O token de autenticação.
        my_ip (str): O IP do nó local que está tentando assumir a liderança.
        current_etag (str): O ETag lido no momento da consulta para garantir atomicidade.
        
    Returns:
        bool: True se o lock foi adquirido com sucesso, False se falhou 
        (ex: Erro 412 Precondition Failed, ou seja, outro nó tomou o lock primeiro).
    """
    # Cabeçalho if-match é obrigatório para a transação atômica
    headers = {
        'if-match': current_etag
    }
    params = {
        'auth': auth_token
    }
    
    # O novo estado, marcando este nó como o líder (ONLINE)
    novo_estado = {
        "status": "ONLINE",
        "host_ativo_ip": my_ip,
        "timestamp_ultimo_save": int(time.time())
    }
    
    try:
        # Usa PUT para substituir os dados completamente
        response = requests.put(URL_CLUSTER, headers=headers, params=params, json=novo_estado, timeout=5.0)
        
        # 200 OK significa que a atualização foi aplicada e o lock foi adquirido
        if response.status_code == 200:
            return True
            
        # 412 Precondition Failed significa que o dado foi alterado por outro nó nesse meio tempo
        if response.status_code == 412:
            print("Conflito: Outro nó adquiriu o lock antes (Erro 412).")
            return False
            
        # Em caso de outros erros, lançar a exceção
        response.raise_for_status()
        return False
        
    except requests.exceptions.Timeout:
        print("Erro: Tempo limite de requisição (Timeout) atingido ao tentar adquirir o lock.")
        return False
    except requests.exceptions.RequestException as e:
        print(f"Erro de rede ao tentar adquirir o lock: {e}")
        return False
