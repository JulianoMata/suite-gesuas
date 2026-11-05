# -*- coding: utf-8 -*-
"""
========================================================================================
SUITE GESUAS - CENTRAL DE OPERAÇÕES INTEGRADA (CRAS SUL - CAMPO BELO / MG)
MÓDULO: INTERFACE GRÁFICA PRINCIPAL DO OPERADOR (app_suite.py)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Ponto de entrada e painel unificado da Suite GESUAS construído em CustomTkinter.
            Disponibiliza arquitetura multithreading por abas para gestão da Auditoria
            Cadastral (cruzamento cronológico de PDFs vs GESUAS) e do Robô de Lançamentos
            (automação em lote via Excel), com lazy loading de módulos pesados,
            telemetria em tempo real, checkpoints e cancelamento controlado.
========================================================================================
"""

import os
import sys
import queue
import threading
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Resolução de diretórios com suporte a PyInstaller (_MEIPASS)
if getattr(sys, 'frozen', False):
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

AUDITOR_DIR = os.path.join(BASE_DIR, "core", "Auditor")
AUTOMACAO_DIR = os.path.join(BASE_DIR, "core", "Automacao")

for caminho in [BASE_DIR, AUDITOR_DIR, AUTOMACAO_DIR]:
    if caminho not in sys.path:
        sys.path.insert(0, caminho)

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class JanelaSobre(ctk.CTkToplevel):
    """Janela Modal com os dados do autor, versão e créditos acadêmicos."""
    def __init__(self, parent):
        super().__init__(parent)

        self.title("Sobre a Suite GESUAS")
        self.geometry("540x430")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.after(10, self._centralizar)

        frame_corpo = ctk.CTkFrame(self, corner_radius=12)
        frame_corpo.pack(fill="both", expand=True, padx=20, pady=20)

        ctk.CTkLabel(
            frame_corpo, 
            text="Suite GESUAS", 
            font=("Segoe UI", 20, "bold"),
            text_color="#3B8ED0"
        ).pack(pady=(15, 2))

        ctk.CTkLabel(
            frame_corpo, 
            text="Central Integrada de Auditoria e Automação Cadastral", 
            font=("Segoe UI", 11, "italic"),
            text_color="gray"
        ).pack(pady=(0, 15))

        ctk.CTkFrame(frame_corpo, height=2, fg_color="#333333").pack(fill="x", padx=25, pady=5)

        info_texto = (
            "• Versão: 2.0.0 (Suite Integrada)\n"
            "• Construção: Novembro / 2026\n"
            "• Unidade: CRAS Sul - Prefeitura Municipal de Campo Belo / MG\n\n"
            "• Autor: Juliano França da Mata\n"
            "• Cargo: Agente Administrativo / Operador do Cadastro Único\n"
            "• Contato / E-mail: jfmatta@gmail.com\n\n"
            "• Formação Acadêmica:\n"
            "   - Bacharel em Ciência de Dados e Inteligência Artificial (UniDomBosco)\n"
            "   - Tecnólogo em Gestão de Tecnologia da Informação (UniCesumar)\n"
            "   - Técnico em Informática"
        )

        lbl_info = ctk.CTkLabel(
            frame_corpo, 
            text=info_texto, 
            font=("Segoe UI", 11), 
            justify="left", 
            anchor="w"
        )
        lbl_info.pack(fill="x", padx=30, pady=10)

        ctk.CTkButton(
            frame_corpo, 
            text="Fechar", 
            width=120, 
            height=30, 
            command=self.destroy
        ).pack(pady=(15, 10))

    def _centralizar(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() // 2) - (540 // 2)
        y = (self.winfo_screenheight() // 2) - (430 // 2)
        self.geometry(f"+{x}+{y}")


class SuiteGesuasApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Suite GESUAS - Painel Integrado de Operações")
        self.geometry("980x820")
        self.minsize(920, 760)

        self.protocol("WM_DELETE_WINDOW", self._ao_fechar_janela)

        self.fila_eventos = queue.Queue()
        self.thread_ativa = None
        self.cancelamento_solicitado = threading.Event()
        self.evento_login_pronto = threading.Event()
        self.var_ignorar_checkpoint = ctk.BooleanVar(value=False)

        self._construir_interface()
        self._monitorar_eventos()

    def _construir_interface(self):
        # Cabeçalho Principal
        frame_cabecalho = ctk.CTkFrame(self, fg_color="transparent")
        frame_cabecalho.pack(fill="x", padx=25, pady=(15, 5))

        frame_titulos = ctk.CTkFrame(frame_cabecalho, fg_color="transparent")
        frame_titulos.pack(side="left", anchor="w")

        ctk.CTkLabel(
            frame_titulos, 
            text="Central de Operações GESUAS", 
            font=("Segoe UI", 22, "bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            frame_titulos, 
            text="CRAS Sul - Campo Belo / MG | Auditoria Cadastral (PDFs) e Automação de Atendimentos (Excel)",
            text_color="gray", 
            font=("Segoe UI", 12)
        ).pack(anchor="w")

        ctk.CTkButton(
            frame_cabecalho,
            text="ℹ️ Sobre o Sistema",
            width=135,
            height=32,
            font=("Segoe UI", 11, "bold"),
            fg_color="#2B2B2B",
            hover_color="#3B3B3B",
            command=self._abrir_sobre
        ).pack(side="right", anchor="e", pady=5)

        # Abas Operacionais
        self.tabview = ctk.CTkTabview(self, height=295)
        self.tabview.pack(fill="x", padx=25, pady=5)

        self.tab_auditoria = self.tabview.add("🔍 1. Auditoria Cadastral (PDFs)")
        self.tab_automacao = self.tabview.add("🤖 2. Robô de Lançamentos (Excel)")

        self._construir_aba_auditoria()
        self._construir_aba_automacao()

        # Barra de Progresso e Métricas
        frame_status = ctk.CTkFrame(self, fg_color="transparent")
        frame_status.pack(fill="x", padx=25, pady=(6, 0))

        self.lbl_status = ctk.CTkLabel(
            frame_status, text="Status: Aguardando seleção de diretórios", 
            font=("Segoe UI", 12, "bold")
        )
        self.lbl_status.pack(side="left")

        self.lbl_pct = ctk.CTkLabel(
            frame_status, text="0%", 
            font=("Segoe UI", 13, "bold"), text_color="#3B8ED0"
        )
        self.lbl_pct.pack(side="right")

        self.barra_progresso = ctk.CTkProgressBar(self, height=14)
        self.barra_progresso.pack(fill="x", padx=25, pady=(4, 8))
        self.barra_progresso.set(0)

        # Log Terminal
        ctk.CTkLabel(self, text="Andamento da Operação:", font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=25)
        self.txt_logs = ctk.CTkTextbox(self, font=("Consolas", 11))
        self.txt_logs.pack(fill="both", expand=True, padx=25, pady=(4, 8))

        # Interrupção de Processamento
        self.btn_cancelar = ctk.CTkButton(
            self,
            text="Interromper Processamento",
            height=36,
            fg_color="#C42B1C",
            hover_color="#9E2216",
            command=self._solicitar_cancelamento,
            state="disabled"
        )
        self.btn_cancelar.pack(fill="x", padx=25, pady=(0, 15))

    def _abrir_sobre(self):
        JanelaSobre(self)

    # --- ABA 1: AUDITORIA ---
    def _construir_aba_auditoria(self):
        tab = self.tab_auditoria
        tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(tab, text="Pasta Raiz dos PDFs (Entrada):", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, padx=10, pady=3, sticky="w"
        )
        self.ent_raiz_pdf = ctk.CTkEntry(
            tab, placeholder_text="Selecione onde estão os anos (ex: E:\\CADASTROUNICO\\DADOS)...", height=30
        )
        self.ent_raiz_pdf.grid(row=0, column=1, padx=(5, 5), pady=3, sticky="ew")
        
        ctk.CTkButton(
            tab, text="Procurar...", width=95, height=30, command=self._sel_raiz_pdf
        ).grid(row=0, column=2, padx=10, pady=3, sticky="w")

        ctk.CTkLabel(tab, text="Pasta de Saída (Resultados):", font=("Segoe UI", 11, "bold")).grid(
            row=1, column=0, padx=10, pady=3, sticky="w"
        )
        self.ent_destino_auditoria = ctk.CTkEntry(
            tab, placeholder_text="Selecione onde salvar os relatórios PDF, Excel e Checkpoints...", height=30
        )
        self.ent_destino_auditoria.grid(row=1, column=1, padx=(5, 5), pady=3, sticky="ew")

        frame_acoes_saida = ctk.CTkFrame(tab, fg_color="transparent")
        frame_acoes_saida.grid(row=1, column=2, padx=10, pady=3, sticky="w")

        ctk.CTkButton(
            frame_acoes_saida, text="Procurar...", width=95, height=30, command=self._sel_destino_auditoria
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            frame_acoes_saida, text="📂 Abrir", width=75, height=30, fg_color="#333333", hover_color="#444444", command=self._abrir_pasta_destino
        ).pack(side="left")

        frame_selecao = ctk.CTkFrame(tab, fg_color="transparent")
        frame_selecao.grid(row=2, column=0, columnspan=2, padx=10, pady=3, sticky="w")

        ctk.CTkLabel(frame_selecao, text="Ano:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 5))
        self.combo_ano = ctk.CTkComboBox(
            frame_selecao, 
            values=["Selecione a Pasta Raiz"], 
            width=160, 
            height=28,
            command=self._ao_mudar_ano,
            state="disabled"
        )
        self.combo_ano.set("Selecione a Pasta Raiz")
        self.combo_ano.pack(side="left", padx=(0, 20))

        ctk.CTkLabel(frame_selecao, text="Mês:", font=("Segoe UI", 11, "bold")).pack(side="left", padx=(0, 5))
        self.combo_mes = ctk.CTkComboBox(
            frame_selecao, 
            values=["Selecione o Ano"], 
            width=160, 
            height=28,
            command=self._ao_mudar_mes,
            state="disabled"
        )
        self.combo_mes.set("Selecione o Ano")
        self.combo_mes.pack(side="left")

        self.chk_ignorar_checkpoint = ctk.CTkCheckBox(
            tab,
            text="Reiniciar auditoria do zero (ignorar checkpoint deste lote)",
            variable=self.var_ignorar_checkpoint,
            font=("Segoe UI", 11),
            checkbox_width=18,
            checkbox_height=18
        )
        self.chk_ignorar_checkpoint.grid(row=3, column=0, columnspan=2, padx=10, pady=(4, 2), sticky="w")

        self.btn_limpar_checkpoint = ctk.CTkButton(
            tab,
            text="🗑️ Limpar Checkpoint do Mês Selecionado",
            width=250,
            height=26,
            font=("Segoe UI", 10, "bold"),
            fg_color="#3A3A3A",
            hover_color="#4A4A4A",
            command=self._limpar_checkpoint_selecionado
        )
        self.btn_limpar_checkpoint.grid(row=4, column=0, columnspan=2, padx=10, pady=(2, 6), sticky="w")

        frame_botoes = ctk.CTkFrame(tab, fg_color="transparent")
        frame_botoes.grid(row=5, column=0, columnspan=3, padx=10, pady=(4, 4), sticky="ew")
        frame_botoes.grid_columnconfigure((0, 1), weight=1)

        self.btn_exec_auditoria = ctk.CTkButton(
            frame_botoes,
            text="1. Iniciar Auditoria dos PDFs",
            height=34,
            font=("Segoe UI", 12, "bold"),
            fg_color="#107C41",
            hover_color="#0b582e",
            command=self._iniciar_auditoria,
            state="disabled"
        )
        self.btn_exec_auditoria.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_confirmar_login = ctk.CTkButton(
            frame_botoes,
            text="2. Confirmar Login GESUAS (Iniciar Busca)",
            height=34,
            font=("Segoe UI", 12, "bold"),
            fg_color="#D83B01",
            hover_color="#A32B00",
            command=self._confirmar_login_gesuas,
            state="disabled"
        )
        self.btn_confirmar_login.grid(row=0, column=1, padx=(5, 0), sticky="ew")

    # --- ABA 2: AUTOMAÇÃO (ROBÔ DE LANÇAMENTOS) ---
    def _construir_aba_automacao(self):
        tab = self.tab_automacao
        tab.grid_columnconfigure(0, weight=0, minsize=215)
        tab.grid_columnconfigure(1, weight=1)
        tab.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(
            tab, 
            text="Pasta das Planilhas (Entrada):", 
            font=("Segoe UI", 11, "bold"),
            anchor="w"
        ).grid(row=0, column=0, padx=(10, 5), pady=3, sticky="w")

        self.ent_pasta_excel = ctk.CTkEntry(
            tab, placeholder_text="Selecione a pasta onde estão as planilhas (ex: ...\\DADOS_BRUTOS)...", height=30
        )
        self.ent_pasta_excel.grid(row=0, column=1, padx=(0, 5), pady=3, sticky="ew")

        ctk.CTkButton(
            tab, text="Procurar...", width=95, height=30, command=self._sel_pasta_planilhas
        ).grid(row=0, column=2, padx=(5, 10), pady=3, sticky="w")

        ctk.CTkLabel(
            tab, 
            text="Arquivo da Planilha (Ano):", 
            font=("Segoe UI", 11, "bold"),
            anchor="w"
        ).grid(row=1, column=0, padx=(10, 5), pady=3, sticky="w")

        self.combo_arquivo_excel = ctk.CTkComboBox(
            tab,
            values=["Selecione a Pasta Primeiro"],
            height=30,
            state="disabled",
            command=self._ao_mudar_arquivo_excel
        )
        self.combo_arquivo_excel.set("Selecione a Pasta Primeiro")
        self.combo_arquivo_excel.grid(row=1, column=1, padx=(0, 5), pady=3, sticky="ew")

        ctk.CTkLabel(
            tab, 
            text="Pasta para Gravar Relatórios:", 
            font=("Segoe UI", 11, "bold"),
            anchor="w"
        ).grid(row=2, column=0, padx=(10, 5), pady=3, sticky="w")

        self.ent_destino_robo = ctk.CTkEntry(
            tab, placeholder_text="Onde salvar os relatórios e cópias geradas...", height=30
        )
        self.ent_destino_robo.grid(row=2, column=1, padx=(0, 5), pady=3, sticky="ew")

        frame_acoes_destino_robo = ctk.CTkFrame(tab, fg_color="transparent")
        frame_acoes_destino_robo.grid(row=2, column=2, padx=(5, 10), pady=3, sticky="w")

        ctk.CTkButton(
            frame_acoes_destino_robo, text="Procurar...", width=95, height=30, command=self._sel_destino_robo
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            frame_acoes_destino_robo, text="📂 Abrir", width=75, height=30, fg_color="#333333", hover_color="#444444", command=self._abrir_pasta_destino_robo
        ).pack(side="left")

        ctk.CTkLabel(
            tab, 
            text="Aba do Mês na Planilha:", 
            font=("Segoe UI", 11, "bold"),
            anchor="w"
        ).grid(row=3, column=0, padx=(10, 5), pady=3, sticky="w")

        frame_linha_mes = ctk.CTkFrame(tab, fg_color="transparent")
        frame_linha_mes.grid(row=3, column=1, padx=(0, 5), pady=3, sticky="ew")

        self.combo_aba_mes = ctk.CTkComboBox(
            frame_linha_mes,
            values=["Selecione o Arquivo Primeiro"],
            width=180,
            height=30,
            state="disabled",
            command=self._ao_mudar_aba_mes
        )
        self.combo_aba_mes.set("Selecione o Arquivo Primeiro")
        self.combo_aba_mes.pack(side="left", padx=(0, 15))

        self.lbl_info_planilha = ctk.CTkLabel(
            frame_linha_mes, 
            text="📊 Nenhuma planilha carregada.", 
            font=("Segoe UI", 11, "italic"),
            text_color="gray"
        )
        self.lbl_info_planilha.pack(side="left")

        frame_botoes_robo = ctk.CTkFrame(tab, fg_color="transparent")
        frame_botoes_robo.grid(row=4, column=0, columnspan=3, padx=10, pady=(12, 4), sticky="ew")
        frame_botoes_robo.grid_columnconfigure((0, 1), weight=1)

        self.btn_exec_robo = ctk.CTkButton(
            frame_botoes_robo,
            text="1. Iniciar Robô de Lançamento",
            height=34,
            font=("Segoe UI", 12, "bold"),
            fg_color="#0f6cbd",
            hover_color="#0e5a9e",
            command=self._iniciar_automacao,
            state="disabled"
        )
        self.btn_exec_robo.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.btn_confirmar_login_robo = ctk.CTkButton(
            frame_botoes_robo,
            text="2. Confirmar Login GESUAS (Iniciar Robô)",
            height=34,
            font=("Segoe UI", 12, "bold"),
            fg_color="#D83B01",
            hover_color="#A32B00",
            command=self._confirmar_login_gesuas,
            state="disabled"
        )
        self.btn_confirmar_login_robo.grid(row=0, column=1, padx=(5, 0), sticky="ew")

    # --- ATUALIZAÇÕES DINÂMICAS: AUDITORIA ---
    def _sel_raiz_pdf(self):
        pasta = filedialog.askdirectory(parent=self, title="Selecione a Pasta Raiz dos Relatórios PDF")
        if not pasta:
            return

        caminho_raiz = os.path.normpath(pasta)
        self.ent_raiz_pdf.delete(0, "end")
        self.ent_raiz_pdf.insert(0, caminho_raiz)

        try:
            anos_encontrados = sorted([
                item for item in os.listdir(caminho_raiz)
                if os.path.isdir(os.path.join(caminho_raiz, item)) and not item.startswith(".")
            ])
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível ler a pasta selecionada:\n{str(e)}", parent=self)
            return

        if anos_encontrados:
            self.combo_ano.configure(values=anos_encontrados, state="normal")
            self.combo_ano.set(anos_encontrados[0])
            self._atualizar_meses(caminho_raiz, anos_encontrados[0])
            self._validar_liberacao_auditoria()
        else:
            self.combo_ano.configure(values=["Nenhum Ano Encontrado"], state="disabled")
            self.combo_ano.set("Nenhum Ano Encontrado")
            self.combo_mes.configure(values=["Vazio"], state="disabled")
            self.combo_mes.set("Vazio")
            self.btn_exec_auditoria.configure(state="disabled")

    def _ao_mudar_ano(self, ano_escolhido):
        caminho_raiz = self.ent_raiz_pdf.get().strip()
        if os.path.isdir(caminho_raiz):
            self._atualizar_meses(caminho_raiz, ano_escolhido)

    def _ao_mudar_mes(self, _=None):
        self._validar_liberacao_auditoria()

    def _atualizar_meses(self, raiz, ano):
        caminho_ano = os.path.join(raiz, ano)
        try:
            meses_encontrados = sorted([
                item for item in os.listdir(caminho_ano)
                if os.path.isdir(os.path.join(caminho_ano, item)) and not item.startswith(".")
            ])
        except Exception:
            meses_encontrados = []

        if meses_encontrados:
            self.combo_mes.configure(values=meses_encontrados, state="normal")
            self.combo_mes.set(meses_encontrados[0])
            self._validar_liberacao_auditoria()
        else:
            self.combo_mes.configure(values=["Nenhum Mês Encontrado"], state="disabled")
            self.combo_mes.set("Nenhum Mês Encontrado")
            self.btn_exec_auditoria.configure(state="disabled")

    def _sel_destino_auditoria(self):
        pasta = filedialog.askdirectory(parent=self, title="Selecione a Pasta para Salvar Resultados da Auditoria")
        if pasta:
            self.ent_destino_auditoria.delete(0, "end")
            self.ent_destino_auditoria.insert(0, os.path.normpath(pasta))
            self._validar_liberacao_auditoria()

    def _validar_liberacao_auditoria(self):
        raiz_valida = os.path.isdir(self.ent_raiz_pdf.get().strip())
        destino_valido = os.path.isdir(self.ent_destino_auditoria.get().strip())
        mes_valido = self.combo_mes.get() not in ["Selecione o Ano", "Vazio", "Nenhum Mês Encontrado", ""]
        
        if raiz_valida and destino_valido and mes_valido:
            self.btn_exec_auditoria.configure(state="normal")
            self.lbl_status.configure(text="Status: Pronto para iniciar auditoria")
        else:
            self.btn_exec_auditoria.configure(state="disabled")

    def _abrir_pasta_destino(self):
        pasta = self.ent_destino_auditoria.get().strip()
        if os.path.isdir(pasta):
            os.startfile(pasta)
        else:
            messagebox.showwarning("Aviso", "A pasta de saída ainda não existe ou não foi informada.", parent=self)

    def _limpar_checkpoint_selecionado(self):
        destino = self.ent_destino_auditoria.get().strip()
        ano = self.combo_ano.get()
        mes = self.combo_mes.get()

        if not os.path.isdir(destino):
            messagebox.showwarning("Atenção", "Selecione uma pasta de saída válida para localizar os checkpoints.", parent=self)
            return

        caminho_arquivo = os.path.join(destino, "CHECKPOINTS", f"checkpoint_{ano}_{mes}.json")

        if not os.path.exists(caminho_arquivo):
            messagebox.showinfo("Checkpoint", f"Não há checkpoint salvo para {ano} / {mes}.", parent=self)
            return

        if messagebox.askyesno("Confirmar Exclusão", f"Deseja resetar o progresso gravado de {ano}/{mes}?\n\nO próximo início auditará desde a família 1.", parent=self):
            try:
                os.remove(caminho_arquivo)
                self.txt_logs.insert("end", f"\n[CHECKPOINT]: Progresso salvo de {ano}_{mes} foi resetado com sucesso.\n")
                self.txt_logs.see("end")
                messagebox.showinfo("Sucesso", "Checkpoint removido! O lote começará da família 1.", parent=self)
            except Exception as e:
                messagebox.showerror("Erro", f"Falha ao apagar arquivo:\n{str(e)}", parent=self)

    # --- ATUALIZAÇÕES DINÂMICAS: ROBÔ DE LANÇAMENTOS ---
    def _sel_pasta_planilhas(self):
        pasta = filedialog.askdirectory(parent=self, title="Selecione a Pasta com as Planilhas Excel")
        if not pasta:
            return

        caminho_pasta = os.path.normpath(pasta)
        self.ent_pasta_excel.delete(0, "end")
        self.ent_pasta_excel.insert(0, caminho_pasta)

        try:
            arquivos = sorted([
                f for f in os.listdir(caminho_pasta)
                if (f.lower().endswith(".xlsx") or f.lower().endswith(".xls")) and not f.startswith("~$")
            ])
        except Exception as e:
            messagebox.showerror("Erro de Leitura", f"Não foi possível listar a pasta:\n{str(e)}", parent=self)
            return

        if arquivos:
            self.combo_arquivo_excel.configure(values=arquivos, state="normal")
            self.combo_arquivo_excel.set(arquivos[0])
            self._carregar_abas_do_arquivo(os.path.join(caminho_pasta, arquivos[0]))
        else:
            self.combo_arquivo_excel.configure(values=["Nenhum arquivo .xlsx encontrado"], state="disabled")
            self.combo_arquivo_excel.set("Nenhum arquivo .xlsx encontrado")
            self.combo_aba_mes.configure(values=["Vazio"], state="disabled")
            self.combo_aba_mes.set("Vazio")
            self.btn_exec_robo.configure(state="disabled")

    def _ao_mudar_arquivo_excel(self, arquivo_escolhido):
        pasta = self.ent_pasta_excel.get().strip()
        caminho_completo = os.path.join(pasta, arquivo_escolhido)
        if os.path.isfile(caminho_completo):
            self._carregar_abas_do_arquivo(caminho_completo)

    def _carregar_abas_do_arquivo(self, caminho_arquivo):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(caminho_arquivo, read_only=True)
            abas = wb.sheetnames
            wb.close()

            if abas:
                self.combo_aba_mes.configure(values=abas, state="normal")
                aba_padrao = "OUTUBRO" if "OUTUBRO" in [str(a).upper() for a in abas] else abas[0]
                self.combo_aba_mes.set(str(aba_padrao))
                self._atualizar_info_aba(caminho_arquivo, aba_padrao)
                self._validar_liberacao_robo()
            else:
                self.combo_aba_mes.configure(values=["Sem Abas"], state="disabled")
                self.combo_aba_mes.set("Sem Abas")
                self.btn_exec_robo.configure(state="disabled")
        except Exception as e:
            self.lbl_info_planilha.configure(text=f"Erro ao ler abas: {str(e)}", text_color="red")
            self.btn_exec_robo.configure(state="disabled")

    def _ao_mudar_aba_mes(self, aba_escolhida):
        pasta = self.ent_pasta_excel.get().strip()
        arquivo = self.combo_arquivo_excel.get().strip()
        caminho_completo = os.path.join(pasta, arquivo)
        if os.path.isfile(caminho_completo):
            self._atualizar_info_aba(caminho_completo, aba_escolhida)

    def _atualizar_info_aba(self, caminho_arquivo, aba):
        try:
            import pandas as pd
            df = pd.read_excel(caminho_arquivo, sheet_name=aba)

            col_nome = next((c for c in df.columns if "NOME" in str(c).upper()), None)
            col_servico = next((c for c in df.columns if "SERVI" in str(c).upper()), None)
            col_gesuas = next((c for c in df.columns if "GESUAS" in str(c).upper()), None)

            if col_nome:
                df = df[df[col_nome].notna() & (df[col_nome].astype(str).str.strip() != "") & (df[col_nome].astype(str).str.upper() != "NAN")]

            total_geral = len(df)
            if total_geral == 0:
                self.lbl_info_planilha.configure(text=f"📊 Aba: {aba} | Planilha vazia.", text_color="gray")
                return

            s_servico = df[col_servico].fillna("").astype(str).str.upper() if col_servico else pd.Series([""] * total_geral)
            s_gesuas = df[col_gesuas].fillna("").astype(str).str.upper() if col_gesuas else pd.Series([""] * total_geral)

            qtd_atualizacao = s_servico.str.contains("ATUALIZA").sum()
            qtd_inclusao = s_servico.str.contains("INCLUSA").sum()
            qtd_exclusao = s_servico.str.contains("EXCLUSA").sum()
            qtd_consulta = s_servico.str.contains("CONSULTA").sum()

            mascara_lancaveis = s_servico.str.contains("ATUALIZA|INCLUSA|EXCLUSA")
            mascara_ok = s_gesuas.str.contains("OK")

            pendentes_reais = (mascara_lancaveis & ~mascara_ok).sum()

            texto_info = (
                f"📊 Total: {total_geral} | "
                f"Atualizações: {qtd_atualizacao} | "
                f"Inclusões: {qtd_inclusao} | "
                f"Consultas: {qtd_consulta} | "
                f"Exclusões: {qtd_exclusao} | "
                f"Pendentes (At/Inc): {pendentes_reais}"
            )

            cor_destaque = "#107C41" if pendentes_reais == 0 else "#3B8ED0"

            self.lbl_info_planilha.configure(
                text=texto_info,
                font=("Segoe UI", 10, "bold"),
                text_color=cor_destaque
            )
        except Exception as e:
            self.lbl_info_planilha.configure(
                text=f"Erro ao analisar métricas da aba: {str(e)}", 
                text_color="#C53030"
            )
            
    def _sel_destino_robo(self):
        pasta = filedialog.askdirectory(parent=self, title="Selecione a Pasta de Saída do Robô")
        if pasta:
            self.ent_destino_robo.delete(0, "end")
            self.ent_destino_robo.insert(0, os.path.normpath(pasta))
            self._validar_liberacao_robo()

    def _validar_liberacao_robo(self):
        pasta_origem = os.path.isdir(self.ent_pasta_excel.get().strip())
        arquivo_sel = self.combo_arquivo_excel.get().strip() not in ["Selecione a Pasta Primeiro", "Nenhum arquivo .xlsx encontrado", ""]
        destino_valido = os.path.isdir(self.ent_destino_robo.get().strip())
        aba_valida = self.combo_aba_mes.get() not in ["Selecione o Arquivo Primeiro", "Sem Abas", "Vazio", ""]

        if pasta_origem and arquivo_sel and destino_valido and aba_valida:
            self.btn_exec_robo.configure(state="normal")
            self.lbl_status.configure(text="Status: Pronto para iniciar robô")
        else:
            self.btn_exec_robo.configure(state="disabled")

    def _abrir_pasta_destino_robo(self):
        pasta = self.ent_destino_robo.get().strip()
        if os.path.isdir(pasta):
            os.startfile(pasta)
        else:
            messagebox.showwarning("Aviso", "A pasta de saída ainda não existe ou não foi informada.", parent=self)

    # --- EXECUÇÃO DAS TAREFAS (LAZY IMPORT) ---
    def _iniciar_auditoria(self):
        raiz_pdf = self.ent_raiz_pdf.get().strip()
        destino = self.ent_destino_auditoria.get().strip()
        ano = self.combo_ano.get()
        mes = self.combo_mes.get()
        forcar_reinicio = self.var_ignorar_checkpoint.get()

        if not os.path.isdir(raiz_pdf):
            messagebox.showwarning("Atenção", "Selecione a pasta raiz dos PDFs de entrada.", parent=self)
            return
        if not os.path.isdir(destino):
            messagebox.showwarning("Atenção", "Selecione uma pasta de saída válida para salvar os resultados.", parent=self)
            return

        pasta_mes = os.path.join(raiz_pdf, ano, mes)

        self._bloquear_controles()
        self.cancelamento_solicitado.clear()
        self.evento_login_pronto.clear()
        self.txt_logs.delete("1.0", "end")
        
        modo_txt = "do início (forçado)" if forcar_reinicio else "com checagem de checkpoint"
        self.lbl_status.configure(text=f"Status: Carregando módulos da auditoria...")

        # Lazy import do motor da auditoria
        from core.Auditor.auditor_engine import processar_auditoria

        self.lbl_status.configure(text=f"Status: Iniciando auditoria para {ano}/{mes} ({modo_txt})...")

        self.thread_ativa = threading.Thread(
            target=processar_auditoria,
            args=(pasta_mes, destino, self.evento_login_pronto, self.fila_eventos, self.cancelamento_solicitado, forcar_reinicio),
            daemon=True
        )
        self.thread_ativa.start()

    def _iniciar_automacao(self):
        pasta_planilhas = self.ent_pasta_excel.get().strip()
        arquivo_sel = self.combo_arquivo_excel.get().strip()
        destino = self.ent_destino_robo.get().strip()
        aba_mes = self.combo_aba_mes.get().strip()

        caminho_planilha = os.path.join(pasta_planilhas, arquivo_sel)

        if not os.path.isfile(caminho_planilha):
            messagebox.showwarning("Atenção", "Selecione uma pasta e um arquivo Excel válido (.xlsx).", parent=self)
            return
        if not os.path.isdir(destino):
            messagebox.showwarning("Atenção", "Selecione uma pasta de destino válida para os relatórios.", parent=self)
            return

        self._bloquear_controles()
        self.cancelamento_solicitado.clear()
        self.evento_login_pronto.clear()
        self.txt_logs.delete("1.0", "end")
        self.lbl_status.configure(text="Status: Carregando módulos do robô...")

        # Lazy import do motor de automação
        from core.Automacao.automacao_engine import processar_automacao

        self.lbl_status.configure(text=f"Status: Iniciando Robô de Lançamentos para {aba_mes}...")

        self.thread_ativa = threading.Thread(
            target=processar_automacao,
            args=(caminho_planilha, destino, aba_mes, self.evento_login_pronto, self.fila_eventos, self.cancelamento_solicitado),
            daemon=True
        )
        self.thread_ativa.start()

    def _confirmar_login_gesuas(self):
        self.evento_login_pronto.set()
        self.btn_confirmar_login.configure(state="disabled")
        self.btn_confirmar_login_robo.configure(state="disabled")
        self.lbl_status.configure(text="Status: Busca autorizada. Operando no GESUAS...")

    def _solicitar_cancelamento(self):
        if self.thread_ativa and self.thread_ativa.is_alive():
            if messagebox.askyesno("Confirmar", "Deseja realmente interromper o processamento em andamento?", parent=self):
                self.cancelamento_solicitado.set()
                self.evento_login_pronto.set()
                self.txt_logs.insert("end", "\n[AVISO]: Interrupção solicitada pelo operador...\n")
                self.txt_logs.see("end")

    def _bloquear_controles(self):
        self.btn_exec_auditoria.configure(state="disabled")
        self.btn_confirmar_login.configure(state="disabled")
        self.btn_limpar_checkpoint.configure(state="disabled")
        self.btn_exec_robo.configure(state="disabled")
        self.btn_confirmar_login_robo.configure(state="disabled")
        self.btn_cancelar.configure(state="normal")
        self.barra_progresso.set(0)
        self.lbl_pct.configure(text="0%")

    def _restaurar_controles(self):
        self._validar_liberacao_auditoria()
        self.btn_confirmar_login.configure(state="disabled")
        self.btn_limpar_checkpoint.configure(state="normal")
        self._validar_liberacao_robo()
        self.btn_confirmar_login_robo.configure(state="disabled")
        self.btn_cancelar.configure(state="disabled")

    def _monitorar_eventos(self):
        try:
            while True:
                ev = self.fila_eventos.get_nowait()
                tipo = ev.get("tipo")

                if tipo == "log":
                    self.txt_logs.insert("end", ev["msg"])
                    self.txt_logs.see("end")

                elif tipo == "aguardar_login":
                    self.txt_logs.insert("end", f"\n[AÇÃO NECESSÁRIA]: {ev['msg']}\n")
                    self.txt_logs.see("end")
                    self.lbl_status.configure(text="Status: Aguardando login no GESUAS (Edge)...")
                    self.btn_confirmar_login.configure(state="normal")
                    self.btn_confirmar_login_robo.configure(state="normal")

                elif tipo == "progresso":
                    self.barra_progresso.set(ev["val"])
                    self.lbl_pct.configure(text=f"{int(ev['val'] * 100)}%")
                    self.txt_logs.insert("end", ev["msg"])
                    self.txt_logs.see("end")

                elif tipo in ("fim_auditoria", "fim_robo"):
                    self._restaurar_controles()
                    pasta_destino = ev.get("pasta_destino", "")
                    
                    if ev.get("sucesso", False):
                        self.barra_progresso.set(1.0)
                        self.lbl_pct.configure(text="100%")
                        self.lbl_status.configure(text="Status: Processo concluído com êxito!")
                        
                        abrir = messagebox.askyesno(
                            "Operação Concluída", 
                            "Processamento finalizado com êxito!\n\nDeseja abrir a pasta com os resultados agora?",
                            parent=self
                        )
                        if abrir and pasta_destino and os.path.exists(pasta_destino):
                            os.startfile(pasta_destino)
                    else:
                        self.lbl_status.configure(text="Status: Finalizado com avisos ou pendências.")

                elif tipo == "cancelado":
                    self._restaurar_controles()
                    self.lbl_status.configure(text="Status: Operação interrompida")
                    self.txt_logs.insert("end", "\n[INTERROMPIDO]: A rotina foi finalizada com segurança.\n")
                    self.txt_logs.see("end")

        except queue.Empty:
            pass

        self.after(60, self._monitorar_eventos)

    def _ao_fechar_janela(self):
        if self.thread_ativa and self.thread_ativa.is_alive():
            self.cancelamento_solicitado.set()
            self.evento_login_pronto.set()
        self.destroy()
        sys.exit(0)


if __name__ == "__main__":
    app = SuiteGesuasApp()
    app.mainloop()
    