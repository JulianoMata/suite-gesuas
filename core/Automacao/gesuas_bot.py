# -*- coding: utf-8 -*-
"""
========================================================================================
SISTEMA DE AUTOMAÇÃO DE ATENDIMENTOS E ATUALIZAÇÃO - GESUAS
MÓDULO: MOTOR DE AUTOMAÇÃO WEB PLAYWRIGHT (gesuas_bot.py)
AUTORIA: Juliano França da Mata
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
DESCRIÇÃO: Implementa o pipeline de navegação assistida na plataforma GESUAS:
            - Inicialização e acoplamento CDP ao Microsoft Edge;
            - Busca inteligente resiliente (CPF de 11 dígitos com fallback por Nome);
            - Tratamento prévio de 'Pessoa Desligada' e múltiplos cadastros familiares;
            - Extração via DOM/JS assíncrono em 'Editar um Atendimento' (Anti-duplicidade);
            - Lançamento de atendimento com data/hora estrita e encerramento operacional.
========================================================================================
"""

import os
import time
import re
import subprocess
from importlib import import_module

# Inclui a raiz do projeto e `core` no caminho de busca dos módulos.
import sys
from pathlib import Path

for _base in (Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[1]):
    if str(_base) not in sys.path:
        sys.path.insert(0, str(_base))

_notificacoes = import_module("SCRIPTS.notificacoes")
alerta_intervencao_manual = _notificacoes.alerta_intervencao_manual
alerta_confirmacao_visual = _notificacoes.alerta_confirmacao_visual
PORTA_DEBUG = import_module("SCRIPTS.config").PORTA_DEBUG


def iniciar_edge():
    """Inicia o Microsoft Edge com porta de depuração remota habilitada."""
    caminhos_edge = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    edge_exe = None
    for caminho in caminhos_edge:
        if os.path.exists(caminho):
            edge_exe = caminho
            break

    if not edge_exe:
        alerta_intervencao_manual(
            "Erro de Inicialização",
            "O executável do Microsoft Edge não foi localizado nos diretórios padrão do Windows."
        )
        return False

    perfil_temp = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "EdgeRPA_Sessao")
    cmd = f'"{edge_exe}" --remote-debugging-port={PORTA_DEBUG} --user-data-dir="{perfil_temp}"'
    subprocess.Popen(cmd, shell=True)
    time.sleep(3)
    return True

def conectar_pagina_gesuas(browser):
    """Localiza a aba ativa do GESUAS ou traz a última aba aberta para foco."""
    context = browser.contexts[0]
    page = None
    for p_aba in context.pages:
        titulo_aba = p_aba.title().lower()
        url_aba = p_aba.url.lower()
        if "gesuas" in url_aba or "gesuas" in titulo_aba or "cras" in titulo_aba:
            page = p_aba
            break

    if not page:
        page = context.pages[-1]

    page.bring_to_front()
    print(f"\n[CONECTADO] Página ativa: {page.title()} ({page.url})")
    return page


def fechar_modal_erro_busca(page):
    """Fecha janelas modais de erro de busca caso o GESUAS emita aviso de CPF/campo."""
    modal_erro = page.locator('.ui-dialog:visible:has-text("Erro ao efetuar busca")')
    if modal_erro.count() > 0 and modal_erro.first.is_visible():
        btn_ok_modal = modal_erro.locator('button:has-text("OK"), .ui-dialog-buttonpane button').first
        if btn_ok_modal.is_visible():
            btn_ok_modal.click()
        else:
            modal_erro.locator('.ui-dialog-titlebar-close').first.click()
        page.wait_for_timeout(600)


def retornar_para_busca(page):
    """Garante retorno ao painel de busca clicando no botão '<' ou na sanfona."""
    btn_seta_voltar = page.locator('button:has-text("Agendar Atendimento"), a:has-text("Agendar Atendimento")').locator('xpath=preceding-sibling::*[1]').first
    if btn_seta_voltar.is_visible():
        btn_seta_voltar.click()
        page.wait_for_timeout(1000)

    campo_cpf = page.locator('#pessoa_search_cpf')
    if not campo_cpf.is_visible():
        aba_buscar = page.locator('text="Buscar pessoa"').first
        if aba_buscar.is_visible():
            aba_buscar.click()
            page.wait_for_timeout(500)


def buscar_municipe(page, nome, cpf, tipo_acao):
    """Executa a busca inteligente por CPF (se 11 dígitos) e fallback por Nome."""
    retornar_para_busca(page)
    campo_cpf = page.locator('#pessoa_search_cpf')

    cpf_digitos = re.sub(r'\D', '', str(cpf)) if cpf and str(cpf).lower() not in ['nan', 'none', 'nat'] else ""
    achou_resultado = False

    # 1. Busca por CPF
    if len(cpf_digitos) == 11:
        campo_cpf.wait_for(state="visible", timeout=5000)
        campo_cpf.click()
        campo_cpf.fill(cpf)
        page.locator('#btn_procurar, button:has-text("Procurar..."), a:has-text("Procurar...")').first.click()
        page.wait_for_timeout(1500)
        fechar_modal_erro_busca(page)

        if not page.locator('text="Não foram encontradas pessoas"').is_visible() and page.locator('text="Pessoas encontradas"').is_visible():
            achou_resultado = True

    # 2. Busca por Nome
    if not achou_resultado:
        print(f"   [!] Buscando diretamente por Nome Completo: {nome}...")
        campo_cpf.fill("")
        fechar_modal_erro_busca(page)

        campo_nome = page.locator('#pessoa_search_nome, input[name*="[nome]"]').first
        if not campo_nome.is_visible():
            campo_nome = page.locator('select:has-text("Nome")').locator('xpath=../following-sibling::input | following-sibling::input').first

        campo_nome.click()
        campo_nome.fill(nome.upper())
        page.locator('#btn_procurar, button:has-text("Procurar..."), a:has-text("Procurar...")').first.click()
        page.wait_for_timeout(1500)
        fechar_modal_erro_busca(page)

    if page.locator('text="Não foram encontradas pessoas"').is_visible() or not page.locator('text="Pessoas encontradas"').is_visible():
        return False
    return True


def verificar_pessoa_desligada_ou_acessar_familia(page, nome, tipo_acao):
    """Verifica se a pessoa está desligada ou se há múltiplos cadastros; acessa família."""
    page.locator('text="Pessoas encontradas"').wait_for(state="visible", timeout=7000)
    page.wait_for_timeout(500)

    bloco_resultado = page.locator('#pessoasListDiv')
    if not bloco_resultado.is_visible():
        bloco_resultado = page.locator('text="Pessoas encontradas"').locator('xpath=ancestor::div[contains(@class, "ui-widget")]').first

    texto_resultado = bloco_resultado.inner_text().lower()

    # Validação de Pessoa Desligada
    if "pessoa desligada" in texto_resultado or "desligada" in texto_resultado:
        print(f"   [AVISO] {nome} consta como 'PESSOA DESLIGADA' ({tipo_acao}). Pulando...")
        modal_add_familia = page.locator('.ui-dialog:visible:has-text("Adicionar à uma Família existente")')
        if modal_add_familia.count() > 0 and modal_add_familia.first.is_visible():
            btn_fechar_dialog = modal_add_familia.locator('.ui-dialog-titlebar-close, button[title="close"], .ui-icon-closethick').first
            if btn_fechar_dialog.is_visible():
                btn_fechar_dialog.click()
                page.wait_for_timeout(600)
        return "DESLIGADA"

    # Múltiplos Cadastros
    linhas_pessoas = page.locator('#pessoasListDiv').locator('text="Código Familiar"')
    if linhas_pessoas.count() > 1:
        alerta_intervencao_manual(
            "GESUAS - Múltiplos Cadastros",
            f"Atenção, Operador!\n\n"
            f"Foram localizados múltiplos cadastros para '{nome}'.\n\n"
            "1. Clique no botão de BONECO da família correta no Edge.\n"
            "2. Após abrir a tela da família, clique em OK neste aviso para continuar."
        )
        page.wait_for_timeout(1000)
    else:
        btn_boneco = page.locator('a[title*="Ver cadastro da família"], button[title*="Ver cadastro da família"]').first
        if not btn_boneco.is_visible():
            btn_boneco = page.locator('#pessoasListDiv .ui-button, #pessoasListDiv button, #pessoasListDiv a').first
        btn_boneco.click(force=True)
        page.wait_for_timeout(2000)

    return "OK"


def checar_duplicidade_atendimento(page, nome, tipo_acao, data_hora_str, data_atend, hora_atend):
    """Abre 'Editar um Atendimento', lê via JS assíncrono e valida duplicidade."""
    btn_editar = page.locator('button:visible:has-text("Editar um Atendimento"), a:visible:has-text("Editar um Atendimento")').first
    btn_editar.wait_for(state="visible", timeout=8000)
    btn_editar.click()
    page.wait_for_timeout(2000)

    texto_historico = page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('.ui-dialog, div[role="dialog"]'))
                             .filter(el => el.offsetWidth > 0 && el.offsetHeight > 0);
        for (const d of dialogs) {
            if (d.innerText.includes('Data do atendimento') || d.innerText.includes('Editar')) {
                return d.innerText;
            }
        }
        return document.body.innerText;
    }""")

    texto_limpo = " ".join(texto_historico.split())
    print(f"   [HISTÓRICO GESUAS LIDO]: {texto_limpo[:130]}...")

    btn_fechar_x = page.locator('.ui-dialog:visible .ui-dialog-titlebar-close, .ui-dialog:visible button[title="close"], .ui-dialog:visible .ui-icon-closethick').first
    if btn_fechar_x.is_visible():
        btn_fechar_x.click()
        page.wait_for_timeout(600)

    ja_cadastrado = False
    if (data_hora_str in texto_limpo) or (data_atend in texto_limpo and hora_atend in texto_limpo):
        ja_cadastrado = True
    elif "Editar" not in texto_limpo and "Data do atendimento" not in texto_limpo:
        ja_cadastrado = alerta_confirmacao_visual(nome, tipo_acao, data_hora_str)

    if ja_cadastrado:
        print(f"   [JÁ CADASTRADO] {tipo_acao} de {data_hora_str} já consta no GESUAS! Clicando no '<'...")
        btn_seta_voltar = page.locator('button:has-text("Agendar Atendimento"), a:has-text("Agendar Atendimento")').locator('xpath=preceding-sibling::*[1]').first
        if not btn_seta_voltar.is_visible():
            btn_seta_voltar = page.locator('a:visible:has-text("<"), button:visible:has-text("<"), .ui-button:has-text("<")').first
        btn_seta_voltar.click()
        page.wait_for_timeout(1500)
        return True

    return False


def registrar_atendimento_e_encerrar(page, data_hora_str, nome, tipo_acao):
    """Preenche data/hora estrita, seleciona a pessoa atendida correta na modal (desmarca RF se não for RF),
    permite intervenção do operador, inicia e encerra atendimento, retornando observação para o relatório PDF."""

    # -------------------------------------------------------------
    # 1. IDENTIFICAÇÃO DO RESPONSÁVEL FAMILIAR (RF)
    # -------------------------------------------------------------
    nome_rf_tela = ""
    try:
        linha_rf = page.locator('tr:has-text("Pessoa de referência")').first
        if linha_rf.is_visible():
            nome_rf_tela = linha_rf.locator('td').first.inner_text().strip()
        else:
            bloco_cod = page.locator('div:has-text("Cód. familiar:")').filter(has_text="Cód. familiar:").last
            if bloco_cod.is_visible():
                primeira_linha = [l.strip() for l in bloco_cod.inner_text().splitlines() if l.strip()][0]
                nome_rf_tela = primeira_linha.split("(")[0].strip()
    except Exception:
        pass

    nome_rf_tela = nome_rf_tela.replace("▲", "").replace("!", "").strip()

    partes_nome = nome.strip().upper().split()
    chave_busca = f"{partes_nome[0]} {partes_nome[1]}" if len(partes_nome) > 1 else partes_nome[0]
    eh_responsavel_familiar = (chave_busca in nome_rf_tela.upper()) if nome_rf_tela else True

    # -------------------------------------------------------------
    # 2. INÍCIO DO ATENDIMENTO NA TELA DA FAMÍLIA
    # -------------------------------------------------------------
    btn_iniciar_tela = page.locator('button:visible:has-text("Iniciar atendimento"), a:visible:has-text("Iniciar atendimento")').filter(has_not=page.locator('#btnNovaFamiliaIniciarAtendimento')).first
    btn_iniciar_tela.wait_for(state="visible", timeout=7000)
    btn_iniciar_tela.click()
    page.wait_for_timeout(1000)

    modal_conteudo = page.locator('#_iniciarAtendimento')
    modal_conteudo.wait_for(state="visible", timeout=10000)
    page.wait_for_timeout(500)

    # -------------------------------------------------------------
    # 3. TRATAMENTO DE NÃO-RF: DESMARCA RF E MARCA MUNÍCIPE DA BUSCA
    # -------------------------------------------------------------
    obs_membro = ""
    if not eh_responsavel_familiar:
        print(f"   [ALERTA MEMBRO] Munícipe atendido ({nome}) NÃO é o Responsável Familiar (RF: {nome_rf_tela})!")
        obs_membro = f" (Não é RF - RF: {nome_rf_tela[:20]})"

        page.evaluate("""(nomeBuscado) => {
            const modal = document.querySelector('#_iniciarAtendimento');
            if (!modal) return;

            const containerPessoas = Array.from(modal.querySelectorAll('div, td, fieldset'))
                                         .find(el => el.innerText && el.innerText.includes('Pessoas atendidas'));
            const escopo = containerPessoas || modal;
            const checkboxes = Array.from(escopo.querySelectorAll('input[type="checkbox"]'));

            checkboxes.forEach(chk => {
                const label = chk.closest('label') || chk.parentElement;
                const texto = label ? label.innerText.toUpperCase() : '';
                if (!texto.includes('JULIANO')) {
                    if (chk.checked) chk.click();
                }
            });

            const partesNome = nomeBuscado.toUpperCase().split(' ').filter(p => p.length > 2);
            for (const chk of checkboxes) {
                const label = chk.closest('label') || chk.parentElement;
                const texto = label ? label.innerText.toUpperCase() : '';
                if (partesNome.some(parte => texto.includes(parte)) && !texto.includes('JULIANO')) {
                    if (!chk.checked) chk.click();
                    break;
                }
            }
        }""", nome)
        page.wait_for_timeout(500)

        alerta_intervencao_manual(
            "GESUAS - Munícipe Não é Responsável Familiar",
            f"Atenção, Operador!\n\n"
            f"Munícipe em Atendimento: {nome}\n"
            f"Responsável Familiar (RF): {nome_rf_tela}\n\n"
            f"O sistema desmarcou o RF e selecionou {nome} na lista de 'Pessoas atendidas'.\n\n"
            "Confira os dados na janela do Edge e clique em OK para prosseguir com o lançamento."
        )

    # -------------------------------------------------------------
    # 4. PREENCHIMENTO ESTRITO DE DATA E HORA
    # -------------------------------------------------------------
    campo_data = modal_conteudo.locator('text="Data do atendimento:"').locator('xpath=following-sibling::input | ../following-sibling::*//input | following::input[1]').first
    if not campo_data.is_visible():
        campo_data = modal_conteudo.locator('input[name*="data"], input[id*="data"]').last

    campo_data.click()
    campo_data.press("Control+A")
    campo_data.press("Backspace")
    campo_data.type(data_hora_str, delay=35)
    page.wait_for_timeout(300)

    btn_fechar_cal = page.locator('button:has-text("Fechar"), .ui-datepicker-close')
    if btn_fechar_cal.is_visible():
        btn_fechar_cal.click()
    else:
        page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    # -------------------------------------------------------------
    # 5. SELEÇÃO DO SERVIÇO: SEM VÍNCULO DE SERVIÇO
    # -------------------------------------------------------------
    select_servico = modal_conteudo.locator('select:has-text("Selecione um Serviço"), select[name*="servico"]').first
    select_servico.select_option(label="Sem vínculo de serviço")
    page.wait_for_timeout(400)

    # -------------------------------------------------------------
    # 6. INICIALIZAÇÃO DA SESSÃO DE ATENDIMENTO NA MODAL
    # -------------------------------------------------------------
    dialog_pai = modal_conteudo.locator('xpath=ancestor::div[contains(@class, "ui-dialog")]').first
    btn_iniciar_modal = dialog_pai.locator('.ui-dialog-buttonpane button:has-text("Iniciar"), button:has-text("Iniciar")').first
    btn_iniciar_modal.click()
    page.wait_for_timeout(2000)

    # -------------------------------------------------------------
    # 7. ENCERRAMENTO DO ATENDIMENTO E MARCAÇÃO DE ATUALIZAÇÃO
    # -------------------------------------------------------------
    btn_encerrar = page.locator('a:has-text("Encerrar atendimento"), button:has-text("Encerrar atendimento")').first
    btn_encerrar.wait_for(state="visible", timeout=10000)
    btn_encerrar.click()
    page.wait_for_timeout(1000)

    modal_encerrar = page.locator('.ui-dialog, div:has-text("Encerrar Atendimento")').filter(has_text="Tipos").last
    modal_encerrar.wait_for(state="visible", timeout=7000)

    opcao_atualizacao = modal_encerrar.locator('text="Cadastramento/Atualização Cadastral na GESUAS"')
    if opcao_atualizacao.is_visible():
        chk = opcao_atualizacao.locator('xpath=preceding-sibling::input | input').first
        if not chk.is_checked():
            opcao_atualizacao.click()
        page.wait_for_timeout(300)

    btn_ok_encerrar = modal_encerrar.locator('button:has-text("OK"), a:has-text("OK")').first
    btn_ok_encerrar.click()
    page.wait_for_timeout(1500)

    # -------------------------------------------------------------
    # 8. RETORNO AO PAINEL DE BUSCA PELO BOTÃO '<'
    # -------------------------------------------------------------
    btn_seta_voltar = page.locator('button:has-text("Agendar Atendimento"), a:has-text("Agendar Atendimento")').locator('xpath=preceding-sibling::*[1]').first
    if btn_seta_voltar.is_visible():
        btn_seta_voltar.click()
    page.wait_for_timeout(1000)

    return obs_membro
