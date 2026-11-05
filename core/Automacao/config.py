# -*- coding: utf-8 -*-
"""
========================================================================================
SISTEMA DE AUTOMAÇÃO DE ATENDIMENTOS E ATUALIZAÇÃO - GESUAS
MÓDULO: CONFIGURAÇÕES GLOBAIS E AMBIENTE (config.py)
AUTORIA: Juliano França da Mata
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
DESCRIÇÃO: Centraliza as definições de diretórios, detecção dinâmica de planilhas
            em DADOS_BRUTOS, relatórios em PDF, porta CDP do Edge e cabeçalho de console.
========================================================================================
"""
import os
import sys
from datetime import datetime

# Estrutura de diretórios híbrida (Script VS Code e .exe no pendrive)
if getattr(sys, 'frozen', False):
    DIRETORIO_RAIZ = os.path.dirname(sys.executable)
else:
    DIRETORIO_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
    DIRETORIO_RAIZ = os.path.dirname(DIRETORIO_SCRIPTS)

# Pasta dedicada para as planilhas anuais de entrada
PASTA_DADOS_BRUTOS = os.path.join(DIRETORIO_RAIZ, "DADOS_BRUTOS")
os.makedirs(PASTA_DADOS_BRUTOS, exist_ok=True)

# Pasta exclusiva para relatórios e recibos em PDF
PASTA_PDF = os.path.join(DIRETORIO_RAIZ, "Relatorios_GESUAS")
os.makedirs(PASTA_PDF, exist_ok=True)

# Porta de depuração remota do Microsoft Edge (CDP)
PORTA_DEBUG = 9222

# Mapeamento padrão dos meses
MESES_PT = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO"
}

# Informações de autoria institucional
AUTOR_NOME = "Juliano França da Mata"
AUTOR_CARGO = "Agente Administrativo / Operador do Cadastro Único - CRAS Sul"
AUTOR_QUALIF = "Bacharel em Ciência de Dados e IA | Tecnólogo em Gestão de TI"


def listar_planilhas_disponiveis():
    """Varre DADOS_BRUTOS e retorna as planilhas Excel encontradas."""
    candidatas = []
    # 1. Busca na pasta DADOS_BRUTOS
    if os.path.exists(PASTA_DADOS_BRUTOS):
        for f in os.listdir(PASTA_DADOS_BRUTOS):
            if f.lower().endswith(".xlsx") and not f.startswith("~$"):
                candidatas.append(os.path.join(PASTA_DADOS_BRUTOS, f))

    # 2. Fallback de contingência na raiz
    if not candidatas and os.path.exists(DIRETORIO_RAIZ):
        for f in os.listdir(DIRETORIO_RAIZ):
            if f.lower().endswith(".xlsx") and not f.startswith("~$"):
                candidatas.append(os.path.join(DIRETORIO_RAIZ, f))

    candidatas.sort()
    return candidatas


def exibir_cabecalho_terminal():
    """Apresenta o cabeçalho no console."""
    print("=" * 80)
    print("      SISTEMA DE AUTOMAÇÃO OPERACIONAL - GESUAS / CRAS SUL")
    print(f"      Data de Execução: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"      Autoria: {AUTOR_NOME} ({AUTOR_QUALIF})")
    print(f"      Cargo: {AUTOR_CARGO}")
    print("=" * 80)
    