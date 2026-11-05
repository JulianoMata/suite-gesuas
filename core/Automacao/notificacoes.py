# -*- coding: utf-8 -*-
"""
========================================================================================
SISTEMA DE AUTOMAÇÃO DE ATENDIMENTOS E ATUALIZAÇÃO - GESUAS
MÓDULO: NOTIFICAÇÕES AUDÍVEIS E INTERVENÇÕES DO OPERADOR (notificacoes.py)
AUTORIA: Juliano França da Mata
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
DESCRIÇÃO: Gerencia os sinais audíveis em canal PCM/frequência (duplo bipe) e janelas
            de diálogo modais sobrepostas (Win32 API / TopMost) para solicitar
            intervenção manual ou confirmação visual do operador sem travar a sessão.
========================================================================================
"""

import time
import ctypes

try:
    import winsound
except ImportError:
    winsound = None


def alerta_intervencao_manual(titulo: str, mensagem: str):
    """Emite 2 bipes audíveis e abre caixa de diálogo sobreposta."""
    try:
        if winsound:
            winsound.Beep(1800, 250)
            time.sleep(0.12)
            winsound.Beep(1800, 250)
    except Exception:
        try:
            if winsound:
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                time.sleep(0.15)
                winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

    # Janela sobreposta (TopMost / MB_ICONWARNING)
    flags = 0x30 | 0x40000 | 0x0
    ctypes.windll.user32.MessageBoxW(0, mensagem, titulo, flags)


def alerta_confirmacao_visual(nome: str, tipo_acao: str, data_hora_str: str) -> bool:
    """Abre pop-up com botões SIM/NÃO para validação de contingência pelo operador."""
    resp = ctypes.windll.user32.MessageBoxW(
        0,
        f"ATENÇÃO OPERADOR (Conferência Visual):\n\n"
        f"Munícipe: {nome}\n"
        f"Ação: {tipo_acao}\n"
        f"Data/Hora na planilha: {data_hora_str}\n\n"
        f"O atendimento dessa Data/Hora JÁ CONSTA na tela do Edge?\n\n"
        f"[SIM] = Já consta (Pular registro e voltar à busca)\n"
        f"[NÃO] = Não consta (Iniciar novo atendimento)",
        "Conferência GESUAS",
        0x24 | 0x40000
    )
    return resp == 6  # 6 == IDYES
