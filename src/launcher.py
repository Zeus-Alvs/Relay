import customtkinter as ctk
import tkinter as tk
import threading
import os
import sys
import json
import shutil
import subprocess
import time
import ctypes
import re
from dotenv import load_dotenv

import pystray
from PIL import Image, ImageDraw

from mente_coletiva import (executar_ciclo_host, release_firebase_lock, encerrar_host_local, 
                            sair_do_relay, deletar_mundo_local, sincronizacao_manual)
from gestor_banco import (cadastrar_usuario, fazer_login, alternar_fila, obter_dados_cluster, 
                          obter_servidores_do_usuario, criar_servidor, resgatar_convite, 
                          deletar_servidor, sair_do_servidor, obter_usuarios_servidor,
                          expulsar_membro, promover_admin, atualizar_tailscale_key)

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(CURRENT_DIR)

DOTENV_PATH = os.path.join(BASE_DIR, "config", ".env")
SESSION_FILE = os.path.join(BASE_DIR, "config", "session.json")
load_dotenv(dotenv_path=DOTENV_PATH)

DB_URL = os.getenv("DB_URL")
AUTH_TOKEN = os.getenv("AUTH_TOKEN")

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

class RelayLauncher(ctk.CTk):
    def __init__(self):
        super().__init__()
        # Interceta o fecho da janela para enviar para a bandeja em segurança
        self.protocol("WM_DELETE_WINDOW", self.esconder_na_bandeja)

        self.title("Relay") 
        self.geometry("400x550")
        self.resizable(False, False)

        # Força o Windows a usar o nosso ícone na barra de tarefas em vez do ícone do Python
        try:
            myappid = 'minetec.relay.launcher.1'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception: pass

        try:
            # Em modo frozen (.exe), o ícone fica na raiz (BASE_DIR) via Inno Setup
            # Em modo dev, fica na pasta src (CURRENT_DIR)
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(BASE_DIR, "relay_ico.ico")
            else:
                icon_path = os.path.join(CURRENT_DIR, "relay_ico.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception as e:
            print(f"[Aviso] Falha ao carregar icone da janela: {e}")

        try:
            subprocess.Popen([r"C:\Program Files\Tailscale\tailscale-ipn.exe"])
        except Exception: pass

        self.is_running = False
        self.logged_user = ""
        self.servidor_atual = "" 
        self.cargo_atual = "membro"
        
        self.waitlist_visible = False
        self.tray_icon = None
        self.is_hidden = False 

        # ==========================================
        # SETUP DO OVERLAY (PÍLULA FLUTUANTE - tkinter puro)
        # ==========================================
        self.overlay = tk.Toplevel(self)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)

        # Cor-chave para transparência (cor que o Windows torna invisível)
        self._cor_transparente = "#010101"
        self.overlay.configure(bg=self._cor_transparente)
        self.overlay.attributes("-transparentcolor", self._cor_transparente)

        # Calcula posição absoluta: canto superior esquerdo
        ov_w, ov_h = 140, 42
        self._ov_x = 20
        self._ov_y = 20

        # Posiciona FORA da tela para mapear sem flash visível
        self.overlay.geometry(f"{ov_w}x{ov_h}+-9999+-9999")
        self.overlay.update()  # Força criação do handle Win32

        # Agora desvincula do parent via Win32 (o handle já existe)
        self._desvincular_overlay_win32()
        self.overlay.withdraw()

        # Seta a posição real para quando for exibido
        self.overlay.geometry(f"{ov_w}x{ov_h}+{self._ov_x}+{self._ov_y}")

        # Widgets do overlay (fundo transparente, só a bolinha e o texto ficam visíveis)
        frame_overlay = tk.Frame(self.overlay, bg=self._cor_transparente, bd=0)
        frame_overlay.pack(fill="both", expand=True)

        self.canvas_dot = tk.Canvas(frame_overlay, width=16, height=16, bg=self._cor_transparente, highlightthickness=0)
        self.canvas_dot.pack(side="left", padx=(15, 5), pady=12)
        self.dot_id = self.canvas_dot.create_oval(2, 2, 14, 14, fill="gray", outline="")

        self.lbl_overlay_text = tk.Label(frame_overlay, text="---", font=("Segoe UI", 11, "bold"), fg="white", bg=self._cor_transparente)
        self.lbl_overlay_text.pack(side="left", padx=(0, 15))

        self.blink_state = False
        self.blink_color = "gray"
        self.overlay_blinking = False

        self.var_overlay_ativo = ctk.BooleanVar(value=True)

        self.frame_welcome = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_register = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_login = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_hub = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_create_server = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_join_server = ctk.CTkFrame(self, fg_color="transparent")
        self.frame_dashboard = ctk.CTkFrame(self, fg_color="transparent")

        self.build_welcome_screen()
        self.build_register_screen()
        self.build_login_screen()
        self.build_hub_screen()
        self.build_create_server_screen()
        self.build_join_server_screen()
        self.build_dashboard_screen()

        # Inicia background tasks
        threading.Thread(target=self.iniciar_tray, daemon=True).start()
        threading.Thread(target=self.monitor_radar_cluster, daemon=True).start()
        
        # Loop nativo seguro
        self.after(2000, self.loop_verificacao_overlay)
        
        self.check_saved_session()

    def show_frame(self, frame):
        for f in (self.frame_welcome, self.frame_register, self.frame_login, 
                  self.frame_hub, self.frame_create_server, self.frame_join_server, self.frame_dashboard):
            f.pack_forget()
        if hasattr(self, 'lbl_reg_status'): self.lbl_reg_status.configure(text="")
        if hasattr(self, 'lbl_log_status'): self.lbl_log_status.configure(text="")
        frame.pack(pady=20, padx=20, fill="both", expand=True)

    def monitor_radar_cluster(self):
        time.sleep(2) 
        while True:
            codigo = self.servidor_atual
            usuario = self.logged_user
            
            # O radar não toca nos botões se você for o Host rodando o servidor!
            if not self.is_running and usuario and codigo:
                dados = obter_dados_cluster(DB_URL, AUTH_TOKEN, codigo)
                if dados:
                    status = dados.get("status", "OFFLINE")
                    host = dados.get("host_ativo_ip", "Ninguém")
                    fila = dados.get("fila", [])
                    
                    texto_fila = "\n".join([f"{i+1}º - {u}" for i, u in enumerate(fila)]) if fila else "Fila Vazia"
                    
                    btn_text = "ENTRAR NO RELAY"
                    btn_fg = "green"
                    btn_hover = "darkgreen"
                    btn_state = "normal"
                    cmd = self.acao_entrar_fila
                    auto_start = False
                    
                    if status == "ONLINE":
                        if host != usuario:
                            if usuario in fila:
                                btn_text = "SAIR DA FILA"
                                btn_fg = "#d47300"
                                btn_hover = "#a85b00"
                                cmd = self.acao_sair_fila
                            else:
                                btn_text = "ENTRAR NO RELAY"
                                btn_fg = "#1f538d"
                                btn_hover = "#14375e"
                                cmd = self.acao_entrar_fila
                    elif status == "OFFLINE":
                        if fila and fila[0] == usuario:
                            auto_start = True
                        elif fila and fila[0] != usuario:
                            btn_text = f"Auto-Start do {fila[0]}..."
                            btn_fg = "gray"
                            btn_state = "disabled"
                            cmd = None
                            
                    self.after(0, self._sync_radar_ui, host, texto_fila, btn_text, btn_fg, btn_hover, btn_state, cmd)
                    
                    if auto_start:
                        self.update_ui_status("A tua vez chegou! A assumir o Bastão...", "green")
                        self.after(0, self.start_orchestrator)
            time.sleep(5)

    def _sync_radar_ui(self, host, texto_fila, btn_text, btn_fg, btn_hover, btn_state, cmd):
        self.lbl_bastao_user.configure(text=host)
        self.lbl_fila.configure(text=texto_fila)
        if cmd:
            self.btn_play.configure(text=btn_text, fg_color=btn_fg, hover_color=btn_hover, state=btn_state, command=cmd)
        else:
            self.btn_play.configure(text=btn_text, fg_color=btn_fg, hover_color=btn_hover, state=btn_state)

    # ==========================================
    # LÓGICA DO WIDGET FLUTUANTE (OVERLAY E LED)
    # ==========================================
    def loop_verificacao_overlay(self):
        """Roda na Thread Principal e garante que o Widget apareça quando minimizado"""
        if self.is_hidden and self.var_overlay_ativo.get(): 
            try:
                # Mostra Host se estiver rodando
                if self.is_running:
                    self.blink_color = "#4CAF50" # Verde Grama
                    self.lbl_overlay_text.configure(text="Host")
                    self.mostrar_overlay()
                # Mostra Fila se estiver na espera
                elif self.lbl_bastao_user.cget("text") != self.logged_user and "SAIR" in self.btn_play.cget("text").upper():
                    self.blink_color = "#FFA500" # Laranja
                    self.lbl_overlay_text.configure(text="Em Fila")
                    self.mostrar_overlay()
                else:
                    self.esconder_overlay()
            except Exception as e:
                print(f"[OVERLAY ERRO] {e}")
        else:
            self.esconder_overlay() 
            
        self.after(2000, self.loop_verificacao_overlay)

    def _obter_hwnd_overlay(self):
        """Obtém o handle Win32 (HWND) real da janela overlay."""
        try:
            self.overlay.update_idletasks()
            hwnd = self.overlay.winfo_id()
            parent = ctypes.windll.user32.GetParent(hwnd)
            resultado = parent if parent else hwnd
            return resultado
        except Exception:
            return None

    def _desvincular_overlay_win32(self):
        """Remove o vínculo owner/parent do overlay no nível do Windows API."""
        hwnd = self._obter_hwnd_overlay()
        if hwnd:
            try:
                ctypes.windll.user32.SetWindowLongPtrW(hwnd, -8, 0)
                print(f"[OVERLAY] Desvinculado do parent com sucesso (HWND: {hwnd})")
            except Exception as e:
                print(f"[OVERLAY] Falha ao desvincular: {e}")
        else:
            print("[OVERLAY] HWND não encontrado para desvincular!")

    def mostrar_overlay(self):
        # Garante a posição correta e mostra via tkinter
        self.overlay.geometry(f"140x42+{self._ov_x}+{self._ov_y}")
        self.overlay.deiconify()
        self.overlay.update_idletasks()
        self.overlay.lift()
        self.overlay.attributes("-topmost", True)

        # Força visibilidade via Win32 API
        hwnd = self._obter_hwnd_overlay()
        if hwnd:
            try:
                ctypes.windll.user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
                ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0053)
            except Exception:
                pass

        if not self.overlay_blinking:
            self.overlay_blinking = True
            self.animar_bolinha()

    def esconder_overlay(self):
        self.overlay.withdraw()
        self.overlay_blinking = False
        try: self.canvas_dot.itemconfig(self.dot_id, fill="gray")
        except Exception: pass

    def animar_bolinha(self):
        if not self.overlay_blinking: return
        self.blink_state = not self.blink_state
        cor_atual = self.blink_color if self.blink_state else self._cor_transparente
        try: self.canvas_dot.itemconfig(self.dot_id, fill=cor_atual)
        except Exception: pass
        self.after(800, self.animar_bolinha)

    def update_ui_status(self, mensagem, cor):
        self.after(0, self._update_ui_status_safe, mensagem, cor)

    def _update_ui_status_safe(self, mensagem, cor):
        self.lbl_status.configure(text=f"Status: {mensagem}", text_color=cor)
        if hasattr(self, 'lbl_overlay_status'):
            self.lbl_overlay_status.configure(text=mensagem, text_color=cor)
            
        # =========================================================
        # A TRAVA DE SEGURANÇA MESTRA DO BOTÃO STOP
        # Só libera quando o log indicar que está "ONLINE"
        # =========================================================
        if self.is_running:
            if "ONLINE" in mensagem.upper():
                self.btn_stop.configure(state="normal") # LIBERA O STOP
                self.btn_play.configure(text="SERVIDOR ONLINE", fg_color="#1f538d", state="disabled")

    # ==========================================
    # LÓGICA DE SYSTEM TRAY (BANDEJA DO SISTEMA)
    # ==========================================
    def gerar_icone_bandeja(self):
        try:
            if getattr(sys, 'frozen', False):
                icon_path = os.path.join(BASE_DIR, "relay_ico.png")
            else:
                icon_path = os.path.join(CURRENT_DIR, "relay_ico.png")
            if os.path.exists(icon_path):
                return Image.open(icon_path)
        except Exception as e:
            print(f"[Aviso] Falha ao carregar icone da bandeja: {e}")
            
        # Fallback se a imagem falhar
        image = Image.new('RGB', (64, 64), color=(31, 83, 141))
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill=(255, 255, 255))
        return image

    def iniciar_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Abrir Relay", self.acao_restaurar_tray, default=True),
            pystray.MenuItem("Encerrar de Vez", self.acao_encerrar_tray)
        )
        self.tray_icon = pystray.Icon("Relay", self.gerar_icone_bandeja(), "Relay Orchestrator", menu)
        self.tray_icon.run()

    def esconder_na_bandeja(self):
        """Minimiza com segurança sem matar threads"""
        self.is_hidden = True
        self.withdraw()
        # Verifica o overlay imediatamente após esconder (não espera os 2s do loop)
        self.after(300, self.loop_verificacao_overlay)

    def acao_restaurar_tray(self, icon, item):
        self.after(0, self._restaurar_janela_principal)

    def _restaurar_janela_principal(self):
        self.is_hidden = False
        self.esconder_overlay()
        self.deiconify()
        self.lift()
        self.attributes('-topmost', True)
        self.after(100, lambda: self.attributes('-topmost', False))

    def acao_encerrar_tray(self, icon, item):
        icon.stop() 
        self.tray_icon = None
        self.after(0, self.forcar_encerramento)

    # ==========================================
    # CONTROLO DE ESTADO (ENTRAR E PARAR) E FILA
    # ==========================================
    def acao_entrar_fila(self):
        self.btn_play.configure(state="disabled", text="ENTRANDO...", fg_color="gray")
        self.start_orchestrator()

    def acao_sair_fila(self):
        self.btn_play.configure(state="disabled", text="A SAIR...", fg_color="gray")
        sair_do_relay(self.logged_user, self.servidor_atual)
        self.update_ui_status("Saíste da fila. VPN desligada.", "gray")

    def toggle_waitlist(self):
        """Alterna a exibição do quadro com a fila de espera"""
        if self.waitlist_visible:
            self.frame_waitlist.pack_forget()
            self.btn_toggle_waitlist.configure(text="Visualizar Fila de Espera ▼")
            self.waitlist_visible = False
        else:
            self.frame_waitlist.pack(after=self.btn_toggle_waitlist, pady=5, fill="x", padx=40)
            self.btn_toggle_waitlist.configure(text="Ocultar Fila de Espera ▲")
            self.waitlist_visible = True

    def start_orchestrator(self):
        """TRAVA TUDO no início do processo"""
        self.is_running = True
        self.btn_play.configure(state="disabled", text="INICIANDO...", fg_color="gray")
        self.btn_stop.configure(state="disabled") # TRAVADO ATÉ FICAR ONLINE
        self.lbl_bastao_user.configure(text=self.logged_user)
        threading.Thread(target=self.run_daemon_background, args=(self.logged_user, self.servidor_atual), daemon=True).start()

    def run_daemon_background(self, usuario, codigo):
        executar_ciclo_host(usuario, codigo, callback_status=self.update_ui_status)
        self.after(0, self.reset_ui_after_teardown)

    def stop_orchestrator(self):
        """TRAVA TUDO na hora de parar para evitar duplo clique"""
        self.update_ui_status("A ENCERRAR! Guardando mapa...", "orange")
        self.btn_stop.configure(state="disabled") # TRAVA 100% IMEDIATAMENTE
        self.btn_play.configure(state="disabled", text="ENCERRANDO...", fg_color="gray")
        encerrar_host_local()

    def reset_ui_after_teardown(self):
        """DESTRAVA quando o ciclo completo termina e o Java morre"""
        self.is_running = False
        self.lbl_bastao_user.configure(text="Ninguém (Vaga Livre)")
        self.btn_play.configure(state="normal", text="ENTRAR NO RELAY", fg_color="green")
        self.btn_stop.configure(state="disabled") # Continua travado, porque o server está offline

    # ==========================================
    # RESTANTE DO CÓDIGO (TELAS, LOGIN, ADMIN)
    # ==========================================
    def check_saved_session(self):
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "r") as f:
                    data = json.load(f)
                    if "logged_user" in data and "nome" in data:
                        self.logged_user = data["logged_user"]
                        self.lbl_hub_welcome.configure(text=f"Bem-vindo(a), {data['nome']}")
                        self.carregar_hub() 
                        return
            except Exception: pass 
        self.show_frame(self.frame_welcome)

    def save_session(self, login, nome):
        with open(SESSION_FILE, "w") as f:
            json.dump({"logged_user": login, "nome": nome}, f)
        self.logged_user = login

    def do_logout(self):
        if os.path.exists(SESSION_FILE): os.remove(SESSION_FILE)
        self.logged_user = ""
        self.servidor_atual = ""
        self.show_frame(self.frame_welcome)

    def build_welcome_screen(self):
        title = ctk.CTkLabel(self.frame_welcome, text="Relay", font=ctk.CTkFont(size=36, weight="bold"))
        title.pack(pady=(60, 10))
        subtitle = ctk.CTkLabel(self.frame_welcome, text="Mente Coletiva Orchestrator", text_color="gray")
        subtitle.pack(pady=(0, 40))
        ctk.CTkButton(self.frame_welcome, text="Criar conta", height=45, command=lambda: self.show_frame(self.frame_register)).pack(pady=10, fill="x", padx=50)
        ctk.CTkLabel(self.frame_welcome, text="Já tens uma conta?", text_color="gray", font=ctk.CTkFont(size=12)).pack(pady=(20, 0))
        ctk.CTkButton(self.frame_welcome, text="Fazer Login", height=45, fg_color="transparent", border_width=2, text_color=("black", "white"), command=lambda: self.show_frame(self.frame_login)).pack(pady=5, fill="x", padx=50)

    def build_register_screen(self):
        ctk.CTkLabel(self.frame_register, text="Criar Conta", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(20, 10))
        self.reg_nome = ctk.CTkEntry(self.frame_register, placeholder_text="Nome / Nickname", height=40)
        self.reg_nome.pack(pady=5, fill="x", padx=40)
        self.reg_login = ctk.CTkEntry(self.frame_register, placeholder_text="Login", height=40)
        self.reg_login.pack(pady=5, fill="x", padx=40)
        self.reg_senha = ctk.CTkEntry(self.frame_register, placeholder_text="Senha", show="*", height=40)
        self.reg_senha.pack(pady=5, fill="x", padx=40)
        self.reg_senha_conf = ctk.CTkEntry(self.frame_register, placeholder_text="Confirmar Senha", show="*", height=40)
        self.reg_senha_conf.pack(pady=5, fill="x", padx=40)
        self.lbl_reg_status = ctk.CTkLabel(self.frame_register, text="", text_color="red", font=ctk.CTkFont(size=12))
        self.lbl_reg_status.pack(pady=(5, 5))
        ctk.CTkButton(self.frame_register, text="Finalizar Registo", height=45, fg_color="green", hover_color="darkgreen", command=self.do_register).pack(pady=(5, 10), fill="x", padx=40)
        ctk.CTkButton(self.frame_register, text="Voltar", height=45, fg_color="transparent", text_color=("black", "white"), command=lambda: self.show_frame(self.frame_welcome)).pack(fill="x", padx=40)

    def build_login_screen(self):
        ctk.CTkLabel(self.frame_login, text="Aceder ao Relay", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(40, 20))
        self.log_login = ctk.CTkEntry(self.frame_login, placeholder_text="Login", height=40)
        self.log_login.pack(pady=10, fill="x", padx=40)
        self.log_senha = ctk.CTkEntry(self.frame_login, placeholder_text="Senha", show="*", height=40)
        self.log_senha.pack(pady=10, fill="x", padx=40)
        self.lbl_log_status = ctk.CTkLabel(self.frame_login, text="", text_color="red", font=ctk.CTkFont(size=12))
        self.lbl_log_status.pack(pady=(5, 5))
        ctk.CTkButton(self.frame_login, text="Entrar", height=45, fg_color="green", command=self.do_login).pack(pady=(5, 10), fill="x", padx=40)
        ctk.CTkButton(self.frame_login, text="Voltar", height=45, fg_color="transparent", text_color=("black", "white"), command=lambda: self.show_frame(self.frame_welcome)).pack(fill="x", padx=40)

    def build_hub_screen(self):
        frame_header = ctk.CTkFrame(self.frame_hub, fg_color="transparent")
        frame_header.pack(fill="x", pady=(0, 10))
        self.lbl_hub_welcome = ctk.CTkLabel(frame_header, text="Olá, Utilizador", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_hub_welcome.pack(side="left")
        ctk.CTkButton(frame_header, text="Sair", width=60, border_width=1, command=self.do_logout).pack(side="right")

        ctk.CTkLabel(self.frame_hub, text="Os Meus Servidores", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(10, 5), anchor="w")
        self.scroll_servidores = ctk.CTkScrollableFrame(self.frame_hub, height=250)
        self.scroll_servidores.pack(fill="x", pady=5)

        ctk.CTkButton(self.frame_hub, text="Entrar com Código", height=40, fg_color="#1f538d", command=lambda: self.show_frame(self.frame_join_server)).pack(pady=(20, 5), fill="x", padx=20)
        ctk.CTkButton(self.frame_hub, text="Criar Novo Servidor", height=40, fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.ir_para_criar_servidor).pack(pady=5, fill="x", padx=20)

    def ir_para_criar_servidor(self):
        motores = self.get_available_motores()
        self.combo_motor_criar.configure(values=motores)
        self.combo_motor_criar.set(motores[-1] if motores else "Vazio")
        self.show_frame(self.frame_create_server)

    def carregar_hub(self):
        # Se houver um processo Rclone pendente de autorização, matá-lo
        if hasattr(self, 'rclone_auth_process') and self.rclone_auth_process:
            try:
                self.rclone_auth_process.kill()
            except Exception: pass
            self.rclone_auth_process = None
            self._falha_gerar_token("Geração cancelada.")

        for widget in self.scroll_servidores.winfo_children(): widget.destroy() 
        servidores = obter_servidores_do_usuario(DB_URL, AUTH_TOKEN, self.logged_user)
        if not servidores:
            ctk.CTkLabel(self.scroll_servidores, text="Não estás em nenhum servidor.", text_color="gray").pack(pady=20)
        else:
            for s in servidores:
                btn = ctk.CTkButton(self.scroll_servidores, text=f"{s['nome']} ({s['cargo'].upper()})", height=40,
                                    command=lambda cod=s['codigo'], n=s['nome'], c=s['cargo'], v=s['versao']: self.abrir_dashboard(cod, n, c, v))
                btn.pack(pady=5, fill="x")
        self.show_frame(self.frame_hub)

    def abrir_dashboard(self, codigo, nome_servidor, cargo, versao):
        self.servidor_atual = codigo
        self.cargo_atual = cargo
        self.lbl_dash_server_name.configure(text=nome_servidor)
        self.lbl_dash_versao.configure(text=f"Motor Blindado: {versao}")
        self.btn_codigo_copia.configure(text=f"Código de Convite: {codigo} 📋")
        
        if versao and versao != "Vazio":
            origem = os.path.join(BASE_DIR, "dependencias", "motores", versao)
            destino = os.path.join(BASE_DIR, "ambiente_teste")
            if not os.path.exists(destino): os.makedirs(destino)
            if os.path.exists(origem):
                try: shutil.copytree(origem, destino, dirs_exist_ok=True)
                except Exception as e: print(f"[Aviso] Erro a transferir ficheiros: {e}")
            
        self.show_frame(self.frame_dashboard)

    def build_create_server_screen(self):
        ctk.CTkLabel(self.frame_create_server, text="Criar Servidor", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(10, 15))
        self.cs_nome = ctk.CTkEntry(self.frame_create_server, placeholder_text="Nome do Servidor")
        self.cs_nome.pack(pady=5, fill="x", padx=20)
        self.cs_ts = ctk.CTkEntry(self.frame_create_server, placeholder_text="Tailscale Auth Key")
        self.cs_ts.pack(pady=5, fill="x", padx=20)
        self.cs_duckd = ctk.CTkEntry(self.frame_create_server, placeholder_text="DuckDNS Domain (ex: omeuserver)")
        self.cs_duckd.pack(pady=5, fill="x", padx=20)
        self.cs_duckt = ctk.CTkEntry(self.frame_create_server, placeholder_text="DuckDNS Token")
        self.cs_duckt.pack(pady=5, fill="x", padx=20)
        # Campo do token (pode continuar como entrada para fallback)
        self.cs_rclone = ctk.CTkEntry(self.frame_create_server, placeholder_text='Token da Drive ({"access_token":...})')
        self.cs_rclone.pack(pady=5, fill="x", padx=20)

        # O NOVO BOTÃO MÁGICO
        self.btn_gerar_rclone = ctk.CTkButton(self.frame_create_server, text="🔗 Autorizar Google Drive Automaticamente", fg_color="#cf8c00", hover_color="#a36e00", command=self.acao_gerar_rclone_token)
        self.btn_gerar_rclone.pack(pady=(0, 5), fill="x", padx=20)

        frame_v = ctk.CTkFrame(self.frame_create_server, fg_color="transparent")
        frame_v.pack(pady=10, fill="x", padx=20)
        ctk.CTkLabel(frame_v, text="Motor de Jogo:").pack(side="left")
        self.combo_motor_criar = ctk.CTkOptionMenu(frame_v, values=["A carregar..."])
        self.combo_motor_criar.pack(side="right")

        self.lbl_create_status = ctk.CTkLabel(self.frame_create_server, text="", text_color="red", font=ctk.CTkFont(size=12))
        self.lbl_create_status.pack(pady=(0, 5))
        ctk.CTkButton(self.frame_create_server, text="Criar e Gerar Convite", fg_color="green", height=40, command=self.acao_criar_servidor).pack(pady=(5, 5), fill="x", padx=20)
        ctk.CTkButton(self.frame_create_server, text="Voltar", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.carregar_hub).pack(pady=5, fill="x", padx=20)

    def build_join_server_screen(self):
        ctk.CTkLabel(self.frame_join_server, text="Resgatar Convite", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(40, 20))
        self.js_codigo = ctk.CTkEntry(self.frame_join_server, placeholder_text="Código de 6 dígitos", height=50, justify="center", font=ctk.CTkFont(size=18, weight="bold"))
        self.js_codigo.pack(pady=10, fill="x", padx=40)
        self.lbl_join_status = ctk.CTkLabel(self.frame_join_server, text="", text_color="red", font=ctk.CTkFont(size=12))
        self.lbl_join_status.pack(pady=(0, 5))
        ctk.CTkButton(self.frame_join_server, text="Vincular à Conta", fg_color="green", height=45, command=self.acao_resgatar_convite).pack(pady=(5, 10), fill="x", padx=40)
        ctk.CTkButton(self.frame_join_server, text="Voltar", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.carregar_hub).pack(fill="x", padx=40)

    def build_dashboard_screen(self):
        frame_header = ctk.CTkFrame(self.frame_dashboard, fg_color="transparent")
        frame_header.pack(fill="x", pady=(0, 10))
        ctk.CTkButton(frame_header, text="◄ Voltar", width=60, border_width=1, fg_color="transparent", text_color=("black", "white"), command=self.voltar_para_hub).pack(side="left")
        self.lbl_dash_server_name = ctk.CTkLabel(frame_header, text="A carregar...", font=ctk.CTkFont(size=20, weight="bold"))
        self.lbl_dash_server_name.pack(side="right")

        self.btn_codigo_copia = ctk.CTkButton(
            self.frame_dashboard, text="A carregar...", fg_color="transparent", 
            border_width=0, text_color="#1f538d", font=ctk.CTkFont(size=14, weight="bold"), 
            hover_color=("gray70", "gray30"), command=self.copiar_codigo
        )
        self.btn_codigo_copia.pack(pady=(0, 10))

        frame_bastao = ctk.CTkFrame(self.frame_dashboard)
        frame_bastao.pack(pady=5, padx=20, fill="x")
        ctk.CTkLabel(frame_bastao, text="Host Atual:", font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(5, 0))
        self.lbl_bastao_user = ctk.CTkLabel(frame_bastao, text="Ninguém (Vaga Livre)", font=ctk.CTkFont(size=16, weight="bold"))
        self.lbl_bastao_user.pack(pady=(0, 5))

        self.btn_toggle_waitlist = ctk.CTkButton(self.frame_dashboard, text="Visualizar Fila de Espera ▼", fg_color="transparent", text_color="gray", hover_color="#2b2b2b", command=self.toggle_waitlist)
        self.btn_toggle_waitlist.pack(pady=0)
        self.frame_waitlist = ctk.CTkFrame(self.frame_dashboard, fg_color="#1a1a1a")
        self.lbl_fila = ctk.CTkLabel(self.frame_waitlist, text="Fila Vazia", justify="left")
        self.lbl_fila.pack(pady=10, padx=20)

        self.lbl_dash_versao = ctk.CTkLabel(self.frame_dashboard, text="Motor Blindado: ...", text_color="gray")
        self.lbl_dash_versao.pack(pady=(10, 5))

        self.lbl_status = ctk.CTkLabel(self.frame_dashboard, text="Status: A aguardar...", text_color="gray")
        self.lbl_status.pack(pady=(5, 5))

        self.sw_overlay = ctk.CTkSwitch(self.frame_dashboard, text="Exibir Bolinha (Overlay)", variable=self.var_overlay_ativo, font=ctk.CTkFont(size=12))
        self.sw_overlay.pack(pady=(0, 10))

        self.btn_play = ctk.CTkButton(self.frame_dashboard, text="ENTRAR NO RELAY", fg_color="green", hover_color="darkgreen", height=45, font=ctk.CTkFont(weight="bold"), command=self.acao_entrar_fila)
        self.btn_play.pack(pady=5, fill="x", padx=40)

        self.btn_stop = ctk.CTkButton(self.frame_dashboard, text="STOP (Encerrar Servidor)", fg_color="red", hover_color="darkred", state="disabled", height=40, command=self.stop_orchestrator)
        self.btn_stop.pack(pady=5, fill="x", padx=40)

        self.btn_configuracoes = ctk.CTkButton(self.frame_dashboard, text="⚙️ Configurações", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.abrir_janela_configuracoes)
        self.btn_configuracoes.pack(pady=(15, 10), fill="x", padx=40)

    def abrir_janela_configuracoes(self):
        janela_cfg = ctk.CTkToplevel(self)
        janela_cfg.title("Configurações do Servidor")
        janela_cfg.geometry("400x500")
        janela_cfg.attributes("-topmost", True)
        janela_cfg.after(100, lambda: janela_cfg.attributes("-topmost", False))
        
        # Centraliza a janela
        janela_cfg.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (400 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (500 // 2)
        janela_cfg.geometry(f"+{x}+{y}")

        # Secção: Gestão de Mundo Local
        frame_world = ctk.CTkFrame(janela_cfg, fg_color="transparent")
        frame_world.pack(pady=(20, 10), fill="x", padx=20)
        btn_download = ctk.CTkButton(frame_world, text="Baixar Mundo", fg_color="#cf8c00", hover_color="#a36e00", command=self.acao_baixar_mundo_manual)
        btn_download.pack(side="left", expand=True, padx=(0, 5))
        btn_delete = ctk.CTkButton(frame_world, text="Deletar Local", fg_color="#8b0000", hover_color="#5e0000", command=self.acao_deletar_mundo)
        btn_delete.pack(side="right", expand=True, padx=(5, 0))

        # Destravamento (Para ambos, caso trave na nuvem)
        btn_reset = ctk.CTkButton(janela_cfg, text="⚠️ Forçar Destravamento", fg_color="transparent", text_color="#8b0000", hover_color="#330000", command=self.forcar_destravamento)
        btn_reset.pack(pady=(10, 20))

        if self.cargo_atual == "admin":
            # Controlos de Admin
            frame_admin = ctk.CTkFrame(janela_cfg, border_width=1, border_color="#cfa015")
            frame_admin.pack(pady=10, fill="x", padx=20)
            ctk.CTkLabel(frame_admin, text="👑 Controles de Administrador", font=ctk.CTkFont(weight="bold"), text_color="#cfa015").pack(pady=(10, 5))
            
            ctk.CTkButton(frame_admin, text="⚙️ Configurações do Servidor", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.abrir_editor_properties).pack(pady=5, fill="x", padx=20)
            ctk.CTkButton(frame_admin, text="Abrir Pasta Local", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.acao_abrir_pasta).pack(pady=5, fill="x", padx=20)
            ctk.CTkButton(frame_admin, text="Upload de Mods/Plugins", fg_color="#cfa015", hover_color="#9e7b10", text_color="black", command=self.acao_forcar_upload_admin).pack(pady=5, fill="x", padx=20)
            ctk.CTkButton(frame_admin, text="🔑 Trocar Auth Key Tailscale", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.abrir_modal_tailscale).pack(pady=5, fill="x", padx=20)
            ctk.CTkButton(frame_admin, text="👥 Gerir Membros do Servidor", fg_color="transparent", border_width=1, text_color=("black", "white"), command=self.abrir_lista_membros).pack(pady=5, fill="x", padx=20)
            ctk.CTkButton(frame_admin, text="🚨 Deletar Servidor (Irreversível)", fg_color="#8b0000", hover_color="#5e0000", command=self.confirmar_delecao_servidor).pack(pady=(5, 15), fill="x", padx=20)
        else:
            # Controlos de Membro
            btn_sair = ctk.CTkButton(janela_cfg, text="🚪 Sair do Servidor", fg_color="#cf8c00", hover_color="#a36e00", command=self.confirmar_saida_servidor)
            btn_sair.pack(pady=20, fill="x", padx=20)

    def abrir_modal_tailscale(self):
        janela_ts = ctk.CTkToplevel(self)
        janela_ts.title("Tailscale")
        janela_ts.geometry("350x230")
        janela_ts.attributes("-topmost", True)
        
        janela_ts.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() // 2) - (350 // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (230 // 2)
        janela_ts.geometry(f"+{x}+{y}")

        ctk.CTkLabel(janela_ts, text="Trocar Auth Key", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(janela_ts, text="Cole a nova chave do Tailscale abaixo:", text_color="gray").pack(pady=(0, 10))
        
        entry_ts = ctk.CTkEntry(janela_ts, placeholder_text="tskey-auth-...", width=280)
        entry_ts.pack(pady=5)
        
        lbl_status = ctk.CTkLabel(janela_ts, text="", text_color="red", font=ctk.CTkFont(size=12))
        lbl_status.pack(pady=(2, 2))
        
        def salvar():
            nova_key = entry_ts.get().strip()
            if not nova_key:
                lbl_status.configure(text="Insira a nova chave!", text_color="red")
                return
            
            sucesso, msg = atualizar_tailscale_key(DB_URL, AUTH_TOKEN, self.servidor_atual, nova_key)
            if sucesso:
                lbl_status.configure(text=msg, text_color="green")
                janela_ts.after(1500, janela_ts.destroy)
            else:
                lbl_status.configure(text=msg, text_color="red")

        ctk.CTkButton(janela_ts, text="Salvar Nova Chave", fg_color="green", hover_color="darkgreen", command=salvar).pack(pady=(5, 10))


    def do_register(self):
        nome = self.reg_nome.get().strip()
        login = self.reg_login.get().strip().lower()
        senha = self.reg_senha.get()
        senha_conf = self.reg_senha_conf.get()
        if not nome or not login or not senha: 
            self.lbl_reg_status.configure(text="Preenche todos os campos!", text_color="red")
            return
        if senha != senha_conf: 
            self.lbl_reg_status.configure(text="As senhas não coincidem!", text_color="red")
            return
        sucesso, msg = cadastrar_usuario(DB_URL, AUTH_TOKEN, login, senha, nome)
        if sucesso:
            self.lbl_reg_status.configure(text="Registo concluído!", text_color="green")
            self.save_session(login, nome)
            self.lbl_hub_welcome.configure(text=f"Bem-vindo(a), {nome}")
            self.after(1000, self.carregar_hub)
        else: self.lbl_reg_status.configure(text=msg, text_color="red")

    def do_login(self):
        login = self.log_login.get().strip().lower()
        senha = self.log_senha.get()
        if not login or not senha: 
            self.lbl_log_status.configure(text="Preenche o utilizador e a senha!", text_color="red")
            return
        sucesso, retorno = fazer_login(DB_URL, AUTH_TOKEN, login, senha)
        if sucesso:
            self.lbl_log_status.configure(text="Login efetuado com sucesso!", text_color="green")
            self.save_session(login, retorno)
            self.lbl_hub_welcome.configure(text=f"Bem-vindo(a), {retorno}")
            self.after(1000, self.carregar_hub)
        else: self.lbl_log_status.configure(text=retorno, text_color="red")

    # ==========================================
    # GERADOR DE TOKEN AUTOMÁTICO
    # ==========================================
    def acao_gerar_rclone_token(self):
        """Inicia o processo invisível do Rclone e aguarda o navegador"""
        self.btn_gerar_rclone.configure(state="disabled", text="⏳ Aguardando Autorização no Navegador...")
        self.lbl_create_status.configure(text="Por favor, faça login no Google no navegador que acabou de abrir.", text_color="orange")
        threading.Thread(target=self._worker_gerar_token, daemon=True).start()

    def _worker_gerar_token(self):
        rclone_exe = os.path.join(BASE_DIR, "dependencias", "rclone.exe")
        comando = [rclone_exe, "authorize", "drive"]
        
        try:
            # creationflags=0x08000000 garante que o terminal CMD preto NÃO vai piscar na tela
            self.rclone_auth_process = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=0x08000000)
            
            # Aguarda até 2 minutos para o utilizador autorizar
            saida, erro = self.rclone_auth_process.communicate(timeout=120)

            # A nossa captura cirúrgica: caça o bloco JSON exato no meio dos logs do Rclone
            match = re.search(r'\{.*"access_token".*\}', saida, re.DOTALL)
            
            if match:
                token_json = match.group(0)
                self.after(0, self._preencher_token_sucesso, token_json)
            else:
                erro_msg = "Autorização cancelada ou falhou."
                if "bind" in erro:
                    erro_msg = "Erro: A porta de autorização está ocupada. Feche processos Rclone zumbis."
                self.after(0, self._falha_gerar_token, erro_msg)
                
        except subprocess.TimeoutExpired:
            if hasattr(self, 'rclone_auth_process') and self.rclone_auth_process:
                self.rclone_auth_process.kill()
            self.after(0, self._falha_gerar_token, "Tempo limite excedido. Tenta novamente.")
        except Exception as e:
            self.after(0, self._falha_gerar_token, f"Erro ao executar Rclone local: {e}")
        finally:
            self.rclone_auth_process = None

    def _preencher_token_sucesso(self, token):
        """Preenche o campo de texto e volta o botão ao normal"""
        self.cs_rclone.delete(0, 'end')
        self.cs_rclone.insert(0, token)
        self.btn_gerar_rclone.configure(state="normal", text="✅ Autorizado com Sucesso!", fg_color="green")
        self.lbl_create_status.configure(text="Google Drive vinculado!", text_color="green")

    def _falha_gerar_token(self, erro):
        """Trata o erro se a pessoa fechar o navegador sem autorizar"""
        self.btn_gerar_rclone.configure(state="normal", text="🔗 Tentar Autorizar Novamente", fg_color="#cf8c00")
        self.lbl_create_status.configure(text=erro, text_color="red")

    def acao_criar_servidor(self):
        nome = self.cs_nome.get().strip()
        ts = self.cs_ts.get().strip()
        duckd = self.cs_duckd.get().strip()
        duckt = self.cs_duckt.get().strip()
        rclone = self.cs_rclone.get().strip()
        motor = self.combo_motor_criar.get()
        if not nome or not ts or not rclone or motor == "Vazio":
            self.lbl_create_status.configure(text="Preenche os campos e seleciona o motor!", text_color="red")
            return
        sucesso, codigo = criar_servidor(DB_URL, AUTH_TOKEN, self.logged_user, nome, ts, duckd, duckt, rclone, motor)
        if sucesso:
            self.lbl_create_status.configure(text="Servidor Criado!", text_color="green")
            self.cs_nome.delete(0, 'end'); self.cs_ts.delete(0, 'end'); self.cs_duckd.delete(0, 'end'); self.cs_duckt.delete(0, 'end'); self.cs_rclone.delete(0, 'end')
            self.after(1000, self.carregar_hub)
        else: self.lbl_create_status.configure(text=codigo, text_color="red")

    def acao_resgatar_convite(self):
        codigo = self.js_codigo.get().strip()
        if not codigo: 
            self.lbl_join_status.configure(text="Introduz o código!", text_color="red")
            return
        sucesso, msg = resgatar_convite(DB_URL, AUTH_TOKEN, self.logged_user, codigo)
        if sucesso:
            self.lbl_join_status.configure(text=msg, text_color="green")
            self.js_codigo.delete(0, 'end')
            self.after(1000, self.carregar_hub)
        else: self.lbl_join_status.configure(text=msg, text_color="red")

    def confirmar_saida_servidor(self):
        if self.is_running:
            self.update_ui_status("Pára o servidor antes de sair!", "red")
            return
            
        janela_conf = ctk.CTkToplevel(self)
        janela_conf.title("SAIR DO SERVIDOR")
        janela_conf.geometry("350x200")
        janela_conf.attributes("-topmost", True)
        
        ctk.CTkLabel(janela_conf, text="Sair do Servidor?", font=ctk.CTkFont(size=18, weight="bold"), text_color="#cf8c00").pack(pady=(20, 10))
        ctk.CTkLabel(janela_conf, text="Irás perder o acesso e precisarás\nde um novo convite para voltar.", justify="center").pack(pady=(0, 20))
        
        frame_btns = ctk.CTkFrame(janela_conf, fg_color="transparent")
        frame_btns.pack(fill="x", padx=20)
        
        ctk.CTkButton(frame_btns, text="Cancelar", fg_color="gray", command=janela_conf.destroy).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(frame_btns, text="SAIR", fg_color="#cf8c00", hover_color="#a36e00", command=lambda: self.executar_saida_servidor(janela_conf)).pack(side="right", expand=True, padx=5)

    def executar_saida_servidor(self, janela):
        codigo = self.servidor_atual
        sucesso, msg = sair_do_servidor(DB_URL, AUTH_TOKEN, self.logged_user, codigo)
        janela.destroy()
        if sucesso:
            self.servidor_atual = ""
            self.cargo_atual = "membro"
            self.carregar_hub()
        else:
            self.update_ui_status(msg, "red")

    def confirmar_delecao_servidor(self):
        if self.is_running:
            self.update_ui_status("Pára o servidor antes de deletar!", "red")
            return
            
        janela_conf = ctk.CTkToplevel(self)
        janela_conf.title("DELETAR SERVIDOR")
        janela_conf.geometry("350x200")
        janela_conf.attributes("-topmost", True)
        
        ctk.CTkLabel(janela_conf, text="Tens a certeza absoluta?", font=ctk.CTkFont(size=18, weight="bold"), text_color="red").pack(pady=(20, 10))
        ctk.CTkLabel(janela_conf, text="Isso apagará o servidor para TODOS os membros\ne não pode ser desfeito.", justify="center").pack(pady=(0, 20))
        
        frame_btns = ctk.CTkFrame(janela_conf, fg_color="transparent")
        frame_btns.pack(fill="x", padx=20)
        
        ctk.CTkButton(frame_btns, text="Cancelar", fg_color="gray", command=janela_conf.destroy).pack(side="left", expand=True, padx=5)
        ctk.CTkButton(frame_btns, text="DELETAR TUDO", fg_color="#8b0000", hover_color="#5e0000", command=lambda: self.executar_delecao_servidor(janela_conf)).pack(side="right", expand=True, padx=5)

    def executar_delecao_servidor(self, janela):
        codigo = self.servidor_atual
        sucesso, msg = deletar_servidor(DB_URL, AUTH_TOKEN, codigo)
        janela.destroy()
        if sucesso:
            self.servidor_atual = ""
            self.cargo_atual = "membro"
            self.carregar_hub()
        else:
            self.update_ui_status(msg, "red")

    def abrir_lista_membros(self):
        codigo = self.servidor_atual
        if not codigo: return
        
        janela = ctk.CTkToplevel(self)
        janela.title("Gerir Membros")
        janela.geometry("450x500")
        janela.attributes("-topmost", True)
        
        ctk.CTkLabel(janela, text="👥 Gerir Membros", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(15, 5))
        lbl_status_membros = ctk.CTkLabel(janela, text="", text_color="green", font=ctk.CTkFont(size=12))
        lbl_status_membros.pack(pady=(0, 5))
        
        scroll_membros = ctk.CTkScrollableFrame(janela)
        scroll_membros.pack(fill="both", expand=True, padx=20, pady=5)
        
        self.carregar_lista_membros(codigo, scroll_membros, lbl_status_membros)
        ctk.CTkButton(janela, text="Fechar", fg_color="transparent", border_width=1, text_color=("black", "white"), command=janela.destroy).pack(pady=(10, 20), padx=40, fill="x")

    def carregar_lista_membros(self, codigo, scroll_membros, lbl_status):
        for widget in scroll_membros.winfo_children(): widget.destroy()
        sucesso, membros = obter_usuarios_servidor(DB_URL, AUTH_TOKEN, codigo)

        if sucesso:
            for m in membros:
                is_me = (m['login'] == self.logged_user)
                cor_cargo = "#cfa015" if m['cargo'] == "admin" else "gray"
                texto_membro = f"{m['nome']} ({m['login']})\nCargo: {m['cargo'].upper()}"
                
                frame_user = ctk.CTkFrame(scroll_membros, fg_color="#2b2b2b" if m['cargo'] == "admin" else "transparent", border_width=1 if is_me else 0)
                frame_user.pack(fill="x", pady=2, padx=2)
                
                ctk.CTkLabel(frame_user, text=texto_membro, text_color=cor_cargo, justify="left").pack(side="left", anchor="w", padx=10, pady=5)
                
                if not is_me:
                    frame_btns = ctk.CTkFrame(frame_user, fg_color="transparent")
                    frame_btns.pack(side="right", padx=10)

                    if m['cargo'] != "admin":
                        btn_admin = ctk.CTkButton(frame_btns, text="⭐ Admin", width=60, height=25, fg_color="#cfa015", hover_color="#9e7b10", text_color="black", 
                                                  command=lambda alvo=m['login']: self.acao_promover_membro(alvo, codigo, scroll_membros, lbl_status))
                        btn_admin.pack(side="left", padx=2)

                    btn_kick = ctk.CTkButton(frame_btns, text="❌ Excluir", width=60, height=25, fg_color="#8b0000", hover_color="#5e0000", 
                                             command=lambda alvo=m['login']: self.acao_expulsar_membro(alvo, codigo, scroll_membros, lbl_status))
                    btn_kick.pack(side="left", padx=2)
        else:
            ctk.CTkLabel(scroll_membros, text="Erro ao carregar membros.", text_color="red").pack(pady=20)

    def acao_promover_membro(self, alvo, codigo, scroll_membros, lbl_status):
        sucesso, msg = promover_admin(DB_URL, AUTH_TOKEN, alvo, codigo)
        lbl_status.configure(text=msg, text_color="green" if sucesso else "red")
        if sucesso: self.carregar_lista_membros(codigo, scroll_membros, lbl_status)

    def acao_expulsar_membro(self, alvo, codigo, scroll_membros, lbl_status):
        sucesso, msg = expulsar_membro(DB_URL, AUTH_TOKEN, alvo, codigo)
        lbl_status.configure(text=msg, text_color="green" if sucesso else "red")
        if sucesso: self.carregar_lista_membros(codigo, scroll_membros, lbl_status)

    def abrir_editor_properties(self):
        caminho_props = os.path.join(BASE_DIR, "ambiente_teste", "server.properties")
        if not os.path.exists(os.path.join(BASE_DIR, "ambiente_teste")):
            os.makedirs(os.path.join(BASE_DIR, "ambiente_teste"))

        props = {
            "pvp": "true", "allow-flight": "false", "online-mode": "true",
            "hardcore": "false", "motd": "Servidor da Mente Coletiva",
            "max-players": "20", "difficulty": "normal"
        }

        if os.path.exists(caminho_props):
            with open(caminho_props, 'r', encoding='utf-8') as f:
                for linha in f:
                    if '=' in linha and not linha.startswith('#'):
                        k, v = linha.strip().split('=', 1)
                        if k in props: props[k] = v

        janela = ctk.CTkToplevel(self)
        janela.title("Configurações do Servidor")
        janela.geometry("400x550")
        janela.attributes("-topmost", True)

        ctk.CTkLabel(janela, text="server.properties", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=10)

        frame_switches = ctk.CTkFrame(janela, fg_color="transparent")
        frame_switches.pack(pady=10, fill="x", padx=20)

        var_pvp = ctk.BooleanVar(value=(props["pvp"] == "true"))
        ctk.CTkSwitch(frame_switches, text="PvP", variable=var_pvp).pack(pady=5, anchor="w")

        var_flight = ctk.BooleanVar(value=(props["allow-flight"] == "true"))
        ctk.CTkSwitch(frame_switches, text="Permitir Voo (allow-flight)", variable=var_flight).pack(pady=5, anchor="w")

        var_online = ctk.BooleanVar(value=(props["online-mode"] == "true"))
        ctk.CTkSwitch(frame_switches, text="Online Mode (Pirata = Off)", variable=var_online).pack(pady=5, anchor="w")

        var_hardcore = ctk.BooleanVar(value=(props["hardcore"] == "true"))
        ctk.CTkSwitch(frame_switches, text="Modo Hardcore", variable=var_hardcore).pack(pady=5, anchor="w")

        ctk.CTkLabel(janela, text="Nome do Servidor (MOTD):").pack(anchor="w", padx=20)
        entry_motd = ctk.CTkEntry(janela)
        entry_motd.insert(0, props["motd"])
        entry_motd.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(janela, text="Máximo de Jogadores:").pack(anchor="w", padx=20)
        entry_max = ctk.CTkEntry(janela)
        entry_max.insert(0, props["max-players"])
        entry_max.pack(fill="x", padx=20, pady=5)

        ctk.CTkLabel(janela, text="Dificuldade:").pack(anchor="w", padx=20)
        entry_diff = ctk.CTkOptionMenu(janela, values=["peaceful", "easy", "normal", "hard"])
        entry_diff.set(props["difficulty"])
        entry_diff.pack(fill="x", padx=20, pady=5)

        ctk.CTkButton(janela, text="Salvar Configurações", fg_color="green", command=lambda: self.salvar_properties(
            janela, caminho_props, var_pvp, var_flight, var_online, var_hardcore, entry_motd, entry_max, entry_diff
        )).pack(pady=20, fill="x", padx=20)

    def salvar_properties(self, janela, caminho, pvp, flight, online, hardcore, motd, max_p, diff):
        novas_props = {
            "pvp": "true" if pvp.get() else "false",
            "allow-flight": "true" if flight.get() else "false",
            "online-mode": "true" if online.get() else "false",
            "hardcore": "true" if hardcore.get() else "false",
            "motd": motd.get().strip(),
            "max-players": max_p.get().strip(),
            "difficulty": diff.get().strip()
        }

        linhas = []
        if os.path.exists(caminho):
            with open(caminho, 'r', encoding='utf-8') as f:
                linhas = f.readlines()

        with open(caminho, 'w', encoding='utf-8') as f:
            for linha in linhas:
                if '=' in linha and not linha.startswith('#'):
                    chave = linha.split('=')[0].strip()
                    if chave in novas_props:
                        f.write(f"{chave}={novas_props[chave]}\n")
                        del novas_props[chave]
                    else:
                        f.write(linha)
                else:
                    f.write(linha)
            
            for k, v in novas_props.items():
                f.write(f"{k}={v}\n")
                
        self.update_ui_status("Configurações salvas localmente. Clique em Upload Admin para enviar!", "green")
        janela.destroy()

    def copiar_codigo(self):
        codigo = self.servidor_atual
        if codigo:
            self.clipboard_clear()
            self.clipboard_append(codigo)
            self.btn_codigo_copia.configure(text=f"Copiado: {codigo} ✔️")
            self.after(2000, lambda: self.btn_codigo_copia.configure(text=f"Código de Convite: {self.servidor_atual} 📋"))

    def acao_deletar_mundo(self):
        if self.is_running: return
        sucesso = deletar_mundo_local()
        msg = "Mundo deletado localmente." if sucesso else "Pasta world não encontrada."
        cor = "green" if sucesso else "orange"
        self.update_ui_status(msg, cor)

    def acao_baixar_mundo_manual(self):
        if self.is_running: return
        self.btn_download.configure(state="disabled")
        threading.Thread(target=self._worker_sync_manual, args=("pull_world",), daemon=True).start()

    def acao_forcar_upload_admin(self):
        if self.is_running: return
        threading.Thread(target=self._worker_sync_manual, args=("push_admin",), daemon=True).start()

    def _worker_sync_manual(self, modo):
        sincronizacao_manual(self.servidor_atual, modo, callback_status=self.update_ui_status)
        self.after(0, lambda: self.btn_download.configure(state="normal"))

    def acao_abrir_pasta(self):
        server_dir = os.path.join(BASE_DIR, "ambiente_teste")
        if not os.path.exists(server_dir): os.makedirs(server_dir)
        os.startfile(server_dir)

    def voltar_para_hub(self):
        if self.is_running:
            self.update_ui_status("Pára o servidor antes de sair!", "red")
            return
        if self.logged_user and self.servidor_atual:
            try: sair_do_relay(self.logged_user, self.servidor_atual)
            except Exception: pass
        self.servidor_atual = "" 
        self.cargo_atual = "membro"
        self.carregar_hub()

    def forcar_destravamento(self):
        if self.servidor_atual:
            release_firebase_lock(self.servidor_atual)
            self.update_ui_status("Servidor destravado à força com sucesso!", "green")

    def forcar_encerramento(self):
        if self.is_running:
            self.update_ui_status("AGUARDA! A guardar mapa...", "red")
            self.stop_orchestrator() 
            self.after(1000, self.aguardar_encerramento)
        else: self.encerrar_de_vez()

    def aguardar_encerramento(self):
        if self.is_running: self.after(1000, self.aguardar_encerramento)
        else: self.encerrar_de_vez()

    def encerrar_de_vez(self):
        if self.logged_user and self.servidor_atual:
            try: sair_do_relay(self.logged_user, self.servidor_atual)
            except Exception: pass
        try: subprocess.run(["taskkill", "/IM", "tailscale-ipn.exe", "/F"], creationflags=0x08000000)
        except Exception: pass
        self.destroy()
        os._exit(0)

    def get_available_motores(self):
        """Lê os motores disponíveis na pasta de dependências."""
        dir_motores = os.path.join(BASE_DIR, "dependencias", "motores")
        if not os.path.exists(dir_motores): 
            os.makedirs(dir_motores)
        pastas = [nome for nome in os.listdir(dir_motores) if os.path.isdir(os.path.join(dir_motores, nome))]
        return pastas if pastas else ["Vazio"]

if __name__ == "__main__":
    app = RelayLauncher()
    app.mainloop()