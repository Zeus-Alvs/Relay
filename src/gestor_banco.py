import requests
import hashlib
import logging
import random
import string

logger = logging.getLogger(__name__)

def _hash_senha(senha):
    return hashlib.sha256(senha.encode()).hexdigest()

def _normalizar_fila(raw_data):
    """Impede o Firebase de quebrar o Python com dicionários no lugar de arrays"""
    if isinstance(raw_data, dict):
        return [v for v in raw_data.values() if v is not None]
    elif isinstance(raw_data, list):
        return [x for x in raw_data if x is not None]
    return []

def _get_base_url(db_url):
    """Limpa a URL raiz para evitar formatação acidental do banco"""
    return db_url.split("/cluster.json")[0].split(".json")[0]

def cadastrar_usuario(db_url, auth_token, login, senha, nome):
    url_base = _get_base_url(db_url)
    url_usuario = f"{url_base}/usuarios/{login}.json"
    
    try:
        resp = requests.get(url_usuario, params={'auth': auth_token}, timeout=5.0)
        if resp.json() is not None:
            return False, "Erro: Este login já está em uso."
            
        dados = {"nome": nome, "senha_hash": _hash_senha(senha)}
        
        req = requests.put(url_usuario, params={'auth': auth_token}, json=dados, timeout=5.0)
        if req.status_code == 200:
            return True, "Cadastro realizado com sucesso!"
        else:
            return False, f"Erro do Firebase: {req.text}"
    except Exception as e:
        logger.error(f"Falha de rede no cadastro: {e}")
        return False, "Erro de conexão com a internet."

def fazer_login(db_url, auth_token, login, senha):
    url_base = _get_base_url(db_url)
    url_usuario = f"{url_base}/usuarios/{login}.json"
    
    try:
        resp = requests.get(url_usuario, params={'auth': auth_token}, timeout=5.0)
        dados = resp.json()
        
        if dados is None: return False, "Usuário não encontrado."
        if dados.get("senha_hash") == _hash_senha(senha): return True, dados.get("nome")
            
        return False, "Senha incorreta."
    except Exception as e:
        logger.error(f"Falha de rede no login: {e}")
        return False, "Erro de conexão com a internet."

def alternar_fila(db_url, auth_token, codigo_servidor, usuario, entrar=True):
    """Adiciona ou remove o utilizador da fila de um servidor específico"""
    url_base = _get_base_url(db_url)
    url_fila = f"{url_base}/servidores/{codigo_servidor}/fila.json"
    
    try:
        resp = requests.get(url_fila, params={'auth': auth_token}, timeout=5.0)
        fila = _normalizar_fila(resp.json())
        
        if entrar:
            if usuario not in fila: fila.append(usuario)
        else:
            if usuario in fila: fila.remove(usuario)
            
        requests.put(url_fila, params={'auth': auth_token}, json=fila, timeout=5.0)
        return True, fila
    except Exception as e:
        logger.error(f"Erro ao gerir fila: {e}")
        return False, []

def obter_dados_cluster(db_url, auth_token, codigo_servidor):
    """Puxa o estado atual e a fila de um servidor específico"""
    url_base = _get_base_url(db_url)
    url_cluster = f"{url_base}/servidores/{codigo_servidor}/cluster.json"
    url_fila = f"{url_base}/servidores/{codigo_servidor}/fila.json"
    
    try:
        # Puxa o status do motor
        resp_cluster = requests.get(url_cluster, params={'auth': auth_token}, timeout=5.0)
        dados = resp_cluster.json() or {}
        
        # Puxa a fila
        resp_fila = requests.get(url_fila, params={'auth': auth_token}, timeout=5.0)
        dados["fila"] = _normalizar_fila(resp_fila.json())
        return dados
    except Exception:
        return {}

def obter_chaves_servidor(db_url, auth_token, codigo_servidor):
    """Baixa as chaves da API (Tailscale, DuckDNS) exclusivas deste servidor"""
    url_base = _get_base_url(db_url)
    url_chaves = f"{url_base}/servidores/{codigo_servidor}/chaves.json"
    
    try:
        resp = requests.get(url_chaves, params={'auth': auth_token}, timeout=5.0)
        chaves = resp.json() or {}
        return chaves
    except Exception as e:
        logger.error(f"Erro ao obter chaves do servidor: {e}")
        return {}

def gerar_codigo_convite(tamanho=6):
    """Gera um código alfanumérico aleatório de 6 dígitos"""
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choice(caracteres) for _ in range(tamanho))

def criar_servidor(db_url, auth_token, login_dono, nome_servidor, ts_key, duck_domain, duck_token, rclone_token, versao_jogo):
    """Cria um novo servidor no banco com validação de conflitos e limite do DuckDNS"""
    url_base = _get_base_url(db_url)
    
    # ==========================================
    # 1. SCANNER DE CONFLITOS E LIMITES
    # ==========================================
    try:
        url_todos_servidores = f"{url_base}/servidores.json"
        resp = requests.get(url_todos_servidores, params={'auth': auth_token}, timeout=5.0)
        todos_servidores = resp.json() or {}
        
        usos_do_duck_token = 0
        
        for cod, dados in todos_servidores.items():
            chaves_existentes = dados.get("chaves", {})
            
            # Trava 1: Domínio Único
            if chaves_existentes.get("duckdns_domain") == duck_domain:
                return False, "Este Domínio DuckDNS já está em uso por outro servidor!"
                
            # Trava 2: VPN Isolada
            if chaves_existentes.get("tailscale_key") == ts_key:
                return False, "Esta Tailscale Key já está em uso. Crie uma nova para isolar a rede!"
                
            # Trava 3: Contador de limite do Token DuckDNS (Máximo 5)
            if chaves_existentes.get("duckdns_token") == duck_token:
                usos_do_duck_token += 1
                
        if usos_do_duck_token >= 5:
            return False, "Este Token do DuckDNS atingiu o limite máximo de 5 domínios (servidores)."
            
    except Exception as e:
        logger.error(f"Erro ao validar chaves exclusivas: {e}")
        return False, "Erro de rede ao validar as chaves de segurança."

    # ==========================================
    # 2. CRIAÇÃO DO SERVIDOR (SE PASSOU NO TESTE)
    # ==========================================
    codigo = gerar_codigo_convite()
    
    url_novo_servidor = f"{url_base}/servidores/{codigo}.json"
    url_perfil_usuario = f"{url_base}/usuarios/{login_dono}/meus_servidores.json"
    
    dados_servidor = {
        "nome": nome_servidor,
        "versao": versao_jogo, 
        "chaves": {
            "tailscale_key": ts_key,
            "duckdns_domain": duck_domain,
            "duckdns_token": duck_token,
            "rclone_token": rclone_token
        },
        "cluster": {
            "status": "OFFLINE",
            "host_ativo_ip": None,
            "timestamp_ultimo_save": 0
        },
        "fila": []
    }
    
    try:
        requests.put(url_novo_servidor, params={'auth': auth_token}, json=dados_servidor, timeout=5.0)
        requests.patch(url_perfil_usuario, params={'auth': auth_token}, json={codigo: "admin"}, timeout=5.0)
        return True, codigo
    except Exception as e:
        logger.error(f"Erro ao criar servidor: {e}")
        return False, "Erro de rede ao criar o servidor."

def obter_servidores_do_usuario(db_url, auth_token, login_usuario):
    """Puxa a lista de todos os servidores aos quais o utilizador tem acesso"""
    url_base = _get_base_url(db_url)
    url_meus_servidores = f"{url_base}/usuarios/{login_usuario}/meus_servidores.json"
    
    try:
        resp = requests.get(url_meus_servidores, params={'auth': auth_token}, timeout=5.0)
        meus_codigos = resp.json() or {}
        
        lista_final = []
        for codigo, cargo in meus_codigos.items():
            # Puxa o Nome
            url_nome = f"{url_base}/servidores/{codigo}/nome.json"
            resp_nome = requests.get(url_nome, params={'auth': auth_token}, timeout=5.0)
            nome = resp_nome.json() or "Servidor Desconhecido"
            
            # Puxa a Versão
            url_versao = f"{url_base}/servidores/{codigo}/versao.json"
            resp_versao = requests.get(url_versao, params={'auth': auth_token}, timeout=5.0)
            versao = resp_versao.json() or "Vazio"
            
            lista_final.append({
                "codigo": codigo,
                "nome": nome,
                "cargo": cargo,
                "versao": versao # <--- AGORA O HUB RECEBE A VERSÃO
            })
            
        return lista_final
    except Exception as e:
        logger.error(f"Erro ao buscar servidores: {e}")
        return []

def resgatar_convite(db_url, auth_token, login_usuario, codigo_convite):
    """Verifica se o código existe, se o usuário já não faz parte, e adiciona como membro"""
    url_base = _get_base_url(db_url)
    codigo_convite = codigo_convite.upper().strip()
    
    url_verificar_servidor = f"{url_base}/servidores/{codigo_convite}/nome.json"
    url_perfil_usuario = f"{url_base}/usuarios/{login_usuario}/meus_servidores.json"
    
    try:
        # 1. Verifica se o servidor existe de fato
        resp = requests.get(url_verificar_servidor, params={'auth': auth_token}, timeout=5.0)
        nome_servidor = resp.json()
        
        if not nome_servidor:
            return False, "Código de convite inválido ou expirado."
            
        # 2. TRAVA DE SEGURANÇA: Verifica se o usuário já está no servidor
        resp_perfil = requests.get(url_perfil_usuario, params={'auth': auth_token}, timeout=5.0)
        meus_servidores_atuais = resp_perfil.json() or {}
        
        if codigo_convite in meus_servidores_atuais:
            return False, "Você já faz parte deste servidor!"
            
        # 3. Vincula o utilizador ao servidor como 'membro' normal
        requests.patch(url_perfil_usuario, params={'auth': auth_token}, json={codigo_convite: "membro"}, timeout=5.0)
        
        return True, f"Entrou no servidor: {nome_servidor}!"
    except Exception as e:
        logger.error(f"Erro ao resgatar convite: {e}")
        return False, "Erro de rede ao validar o convite."

def deletar_servidor(db_url, auth_token, codigo_servidor):
    """Deleta o servidor da nuvem e remove a referência de todos os usuários (Limpeza de Órfãos)"""
    url_base = _get_base_url(db_url)
    
    try:
        # 1. Apaga o nó do servidor inteiro da nuvem
        url_servidor = f"{url_base}/servidores/{codigo_servidor}.json"
        requests.delete(url_servidor, params={'auth': auth_token}, timeout=5.0)
        
        # 2. Varre os usuários e arranca o código do perfil de quem tinha ele
        url_usuarios = f"{url_base}/usuarios.json"
        resp_users = requests.get(url_usuarios, params={'auth': auth_token}, timeout=5.0)
        usuarios = resp_users.json() or {}
        
        for login, dados in usuarios.items():
            if "meus_servidores" in dados and codigo_servidor in dados["meus_servidores"]:
                url_ref = f"{url_base}/usuarios/{login}/meus_servidores/{codigo_servidor}.json"
                requests.delete(url_ref, params={'auth': auth_token}, timeout=5.0)
                
        return True, "Servidor deletado com sucesso."
    except Exception as e:
        logger.error(f"Erro ao deletar servidor: {e}")
        return False, "Erro de rede ao tentar deletar o servidor."

def sair_do_servidor(db_url, auth_token, login_usuario, codigo_servidor):
    """Remove o usuário do servidor (apaga o código do perfil dele)"""
    url_base = _get_base_url(db_url)
    url_ref = f"{url_base}/usuarios/{login_usuario}/meus_servidores/{codigo_servidor}.json"
    
    try:
        requests.delete(url_ref, params={'auth': auth_token}, timeout=5.0)
        return True, "Você saiu do servidor."
    except Exception as e:
        logger.error(f"Erro ao sair do servidor: {e}")
        return False, "Erro de rede ao tentar sair do servidor."

def obter_usuarios_servidor(db_url, auth_token, codigo_servidor):
    """Varre o banco de dados e retorna todos os usuários que fazem parte do servidor"""
    url_base = _get_base_url(db_url)
    url_usuarios = f"{url_base}/usuarios.json"
    
    try:
        resp = requests.get(url_usuarios, params={'auth': auth_token}, timeout=5.0)
        todos_usuarios = resp.json() or {}
        
        lista_usuarios = []
        for login, dados in todos_usuarios.items():
            # Se o usuário tem a chave 'meus_servidores' e o código está lá dentro
            if "meus_servidores" in dados and codigo_servidor in dados["meus_servidores"]:
                cargo = dados["meus_servidores"][codigo_servidor]
                nome = dados.get("nome", login)
                lista_usuarios.append({"login": login, "nome": nome, "cargo": cargo})
                
        # Organiza a lista: Admins primeiro, depois os membros em ordem alfabética
        lista_usuarios.sort(key=lambda x: (x['cargo'] != 'admin', x['nome']))
        return True, lista_usuarios
    except Exception as e:
        logger.error(f"Erro ao buscar usuários do servidor: {e}")
        return False, "Erro ao buscar a lista de usuários."

def expulsar_membro(db_url, auth_token, login_alvo, codigo_servidor):
    """Remove um usuário do servidor pelo Admin"""
    url_base = _get_base_url(db_url)
    url_ref = f"{url_base}/usuarios/{login_alvo}/meus_servidores/{codigo_servidor}.json"
    try:
        requests.delete(url_ref, params={'auth': auth_token}, timeout=5.0)
        return True, f"Usuário expulso com sucesso."
    except Exception as e:
        logger.error(f"Erro ao expulsar membro: {e}")
        return False, "Erro de rede ao expulsar."

def promover_admin(db_url, auth_token, login_alvo, codigo_servidor):
    """Promove um membro a administrador"""
    url_base = _get_base_url(db_url)
    url_ref = f"{url_base}/usuarios/{login_alvo}/meus_servidores.json"
    try:
        requests.patch(url_ref, params={'auth': auth_token}, json={codigo_servidor: "admin"}, timeout=5.0)
        return True, f"Usuário promovido a Admin!"
    except Exception as e:
        logger.error(f"Erro ao promover admin: {e}")
        return False, "Erro de rede ao promover."

def atualizar_tailscale_key(db_url, auth_token, codigo_servidor, nova_key):
    """Atualiza a Tailscale Auth Key do servidor"""
    url_base = _get_base_url(db_url)
    url_chaves = f"{url_base}/servidores/{codigo_servidor}/chaves.json"
    try:
        requests.patch(url_chaves, params={'auth': auth_token}, json={"tailscale_key": nova_key}, timeout=5.0)
        return True, "Auth Key do Tailscale atualizada com sucesso!"
    except Exception as e:
        logger.error(f"Erro ao atualizar chave do tailscale: {e}")
        return False, "Erro de rede ao atualizar a chave."