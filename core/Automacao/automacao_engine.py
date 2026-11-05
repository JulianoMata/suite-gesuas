# -*- coding: utf-8 -*-
"""
========================================================================================
SUITE GESUAS - CENTRAL DE OPERAÇÕES INTEGRADA (CRAS SUL - CAMPO BELO / MG)
MÓDULO: MOTOR DE AUTOMAÇÃO WEB PLAYWRIGHT (automacao_engine.py / gesuas_bot)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Orquestra o pipeline de lançamentos da Suite GESUAS herdando a engenharia
            do gesuas_bot.py:
            - Conexão CDP ao Edge na porta de depuração (9222);
            - Busca inteligente resiliente (CPF de 11 dígitos com fallback por Nome);
            - Tratamento de 'Pessoa Desligada' e múltiplos cadastros;
            - Extração profunda em 'Editar um Atendimento' (Anti-duplicidade via DOM JS);
            - Ajuste de Não-RF com desmarcação dinâmica de checkboxes;
            - Preenchimento estrito de data/hora (delay 35ms), Sem vínculo de serviço;
            - Atualização de Código Familiar, limpeza de Telefone e Demanda Espontânea;
            - Encerramento com 'Cadastramento/Atualização Cadastral' e retorno por '<';
            - Preserva a planilha original e gera cópia sincronizada em PLANILHAS_EXCEL;
            - Geração de relatório analítico em Excel e relatório oficial em PDF.
========================================================================================
"""

import os
import sys
import re
import time
import subprocess
from datetime import datetime, date, time as datetime_time
import pandas as pd
from playwright.sync_api import sync_playwright

DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_ATUAL not in sys.path:
    sys.path.insert(0, DIRETORIO_ATUAL)

import relatorio_pdf


def formatar_data_segura(valor) -> str:
    """Converte valores de data da planilha para DD/MM/AAAA, sem falhar com NaT ou nulos."""
    if valor is None or pd.isna(valor):
        return ""
    if isinstance(valor, (datetime, date)):
        try:
            return valor.strftime("%d/%m/%Y")
        except Exception:
            return ""

    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "nat", "none"}:
        return ""
    data = pd.to_datetime(texto, dayfirst=True, errors="coerce")
    return "" if pd.isna(data) else data.strftime("%d/%m/%Y")


def formatar_hora_segura(valor) -> str:
    """Converte valores de hora da planilha para HH:MM, sem falhar com NaT ou nulos."""
    if valor is None or pd.isna(valor):
        return ""
    if isinstance(valor, (datetime, datetime_time)):
        try:
            return valor.strftime("%H:%M")
        except Exception:
            pass

    texto = str(valor).strip()
    if not texto or texto.lower() in {"nan", "nat", "none"}:
        return ""
    
    m_h = re.search(r'(\d{1,2}:\d{2})', texto)
    if m_h:
        return m_h.group(1).zfill(5)

    hora = pd.to_datetime(texto, errors="coerce")
    return "" if pd.isna(hora) else hora.strftime("%H:%M")


def iniciar_edge():
    """Inicia o Microsoft Edge com porta de depuração remota 9222 habilitada."""
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
        return False

    perfil_temp = os.path.join(os.environ.get("TEMP", r"C:\Temp"), "EdgeRPA_Sessao")
    cmd = f'"{edge_exe}" --remote-debugging-port=9222 --user-data-dir="{perfil_temp}"'
    subprocess.Popen(cmd, shell=True)
    time.sleep(2)
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
    return page


def fechar_modal_erro_busca(page):
    """Fecha janelas modais de erro de busca caso o GESUAS emita aviso de CPF/campo."""
    try:
        modal_erro = page.locator('.ui-dialog:visible:has-text("Erro ao efetuar busca")')
        if modal_erro.count() > 0 and modal_erro.first.is_visible():
            btn_ok_modal = modal_erro.locator('button:has-text("OK"), .ui-dialog-buttonpane button').first
            if btn_ok_modal.is_visible():
                btn_ok_modal.click()
            else:
                modal_erro.locator('.ui-dialog-titlebar-close').first.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


def retornar_para_busca(page):
    """Garante retorno ao painel de busca clicando no botão '<' ou na sanfona."""
    try:
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
    except Exception:
        pass


def buscar_municipe(page, nome, cpf, fila):
    """Executa a busca inteligente por CPF (se 11 dígitos) e fallback por Nome."""
    retornar_para_busca(page)
    campo_cpf = page.locator('#pessoa_search_cpf')

    cpf_digitos = re.sub(r'\D', '', str(cpf)) if cpf and str(cpf).lower() not in ['nan', 'none', 'nat'] else ""
    achou_resultado = False

    # 1. Busca por CPF
    if len(cpf_digitos) == 11:
        campo_cpf.wait_for(state="visible", timeout=5000)
        campo_cpf.click()
        campo_cpf.fill(cpf_digitos)
        page.locator('#btn_procurar, button:has-text("Procurar..."), a:has-text("Procurar...")').first.click()
        page.wait_for_timeout(1500)
        fechar_modal_erro_busca(page)

        if not page.locator('text="Não foram encontradas pessoas"').is_visible() and page.locator('text="Pessoas encontradas"').is_visible():
            achou_resultado = True

    # 2. Busca por Nome (Fallback)
    if not achou_resultado:
        fila.put({"tipo": "log", "msg": f"   [!] CPF não localizou. Buscando diretamente por Nome: {nome}...\n"})
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


def verificar_pessoa_desligada_ou_acessar_familia(page, nome, fila):
    """Verifica se a pessoa está desligada ou se há múltiplos cadastros; acessa família."""
    page.locator('text="Pessoas encontradas"').wait_for(state="visible", timeout=7000)
    page.wait_for_timeout(500)

    bloco_resultado = page.locator('#pessoasListDiv')
    if not bloco_resultado.is_visible():
        bloco_resultado = page.locator('text="Pessoas encontradas"').locator('xpath=ancestor::div[contains(@class, "ui-widget")]').first

    texto_resultado = bloco_resultado.inner_text().lower()

    if "pessoa desligada" in texto_resultado or "desligada" in texto_resultado:
        fila.put({"tipo": "log", "msg": f"   [AVISO] {nome} consta como 'PESSOA DESLIGADA'. Pulando...\n"})
        modal_add_familia = page.locator('.ui-dialog:visible:has-text("Adicionar à uma Família existente")')
        if modal_add_familia.count() > 0 and modal_add_familia.first.is_visible():
            btn_fechar_dialog = modal_add_familia.locator('.ui-dialog-titlebar-close, button[title="close"], .ui-icon-closethick').first
            if btn_fechar_dialog.is_visible():
                btn_fechar_dialog.click()
                page.wait_for_timeout(600)
        return "DESLIGADA"

    linhas_pessoas = page.locator('#pessoasListDiv').locator('text="Código Familiar"')
    if linhas_pessoas.count() > 1:
        fila.put({"tipo": "log", "msg": f"   [AVISO] Múltiplos cadastros para '{nome}'. Acesse a família no Edge manualmente se necessário.\n"})
        page.wait_for_timeout(1500)
    
    btn_boneco = page.locator('a[title*="Ver cadastro da família"], button[title*="Ver cadastro da família"]').first
    if not btn_boneco.is_visible():
        btn_boneco = page.locator('#pessoasListDiv .ui-button, #pessoasListDiv button, #pessoasListDiv a').first
    btn_boneco.click(force=True)
    page.wait_for_timeout(2000)

    return "OK"


def checar_duplicidade_atendimento(page, data_hora_str, data_atend, hora_atend, fila):
    """Abre 'Editar um Atendimento', lê via JS assíncrono e valida duplicidade."""
    btn_editar = page.locator('button:visible:has-text("Editar um Atendimento"), a:visible:has-text("Editar um Atendimento")').first
    try:
        btn_editar.wait_for(state="visible", timeout=6000)
    except Exception:
        return False

    btn_editar.click()
    page.wait_for_timeout(1500)

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

    btn_fechar_x = page.locator('.ui-dialog:visible .ui-dialog-titlebar-close, .ui-dialog:visible button[title="close"], .ui-dialog:visible .ui-icon-closethick').first
    if btn_fechar_x.is_visible():
        btn_fechar_x.click()
        page.wait_for_timeout(600)

    ja_cadastrado = False
    if (data_hora_str in texto_limpo) or (data_atend in texto_limpo and hora_atend in texto_limpo):
        ja_cadastrado = True

    if ja_cadastrado:
        fila.put({"tipo": "log", "msg": f"   [JÁ CADASTRADO] Atendimento de {data_hora_str} já consta no GESUAS! Retornando...\n"})
        btn_seta_voltar = page.locator('button:has-text("Agendar Atendimento"), a:has-text("Agendar Atendimento")').locator('xpath=preceding-sibling::*[1]').first
        if not btn_seta_voltar.is_visible():
            btn_seta_voltar = page.locator('a:visible:has-text("<"), button:visible:has-text("<")').first
        if btn_seta_voltar.is_visible():
            btn_seta_voltar.click()
        page.wait_for_timeout(1500)
        return True

    return False


def registrar_atendimento_completo(page, data_hora_str, nome, cod_fam_planilha, fila):
    """Executa o lançamento de atendimento com o pipeline refinado do gesuas_bot."""
    # 1. Identificação do RF
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

    # 2. Iniciar atendimento na tela da família
    btn_iniciar_tela = page.locator('button:visible:has-text("Iniciar atendimento"), a:visible:has-text("Iniciar atendimento")').filter(has_not=page.locator('#btnNovaFamiliaIniciarAtendimento')).first
    btn_iniciar_tela.wait_for(state="visible", timeout=7000)
    btn_iniciar_tela.click()
    page.wait_for_timeout(1000)

    modal_conteudo = page.locator('#_iniciarAtendimento')
    modal_conteudo.wait_for(state="visible", timeout=10000)
    page.wait_for_timeout(500)

    # 3. Tratamento de Não-RF
    obs_membro = ""
    if not eh_responsavel_familiar:
        fila.put({"tipo": "log", "msg": f"   [ALERTA MEMBRO] Munícipe ({nome}) NÃO é o RF (RF na tela: {nome_rf_tela}). Ajustando checkboxes...\n"})
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

    # 4. Preenchimento estrito de Data e Hora
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

    # 5. Serviço Socioassistencial: Sem vínculo de serviço com disparo de eventos
    select_servico = modal_conteudo.locator('select:has-text("Selecione um Serviço"), select[name*="servico"]').first
    select_servico.focus()
    select_servico.select_option(label="Sem vínculo de serviço")
    select_servico.dispatch_event("change")
    select_servico.dispatch_event("input")
    page.wait_for_timeout(500)

    # 6. Iniciar atendimento no modal
    dialog_pai = modal_conteudo.locator('xpath=ancestor::div[contains(@class, "ui-dialog")]').first
    btn_iniciar_modal = dialog_pai.locator('.ui-dialog-buttonpane button:has-text("Iniciar"), button:has-text("Iniciar")').first
    btn_iniciar_modal.click()
    page.wait_for_timeout(2000)

    # 7. Editar Família (Código Familiar, Telefone e Demanda)
    fila.put({"tipo": "log", "msg": " -> Acessando 'Editar família' para saneamento cadastral...\n"})
    btn_editar_fam = page.locator('button:visible:has-text("Editar família"), a:visible:has-text("Editar família")').first
    try:
        btn_editar_fam.wait_for(state="visible", timeout=6000)
        btn_editar_fam.click()
        page.wait_for_timeout(1000)
    except Exception as e_ed:
        fila.put({"tipo": "log", "msg": f"   [AVISO]: Botão 'Editar família' não clicável ({str(e_ed)}).\n"})

    modal_fam = page.locator('.ui-dialog:visible:has-text("Editar família"), div[role="dialog"]:visible:has-text("Editar família")').last
    if modal_fam.is_visible():
        # 7.1. Código Familiar
        if cod_fam_planilha and str(cod_fam_planilha).strip() and str(cod_fam_planilha).lower() not in ['nan', 'none']:
            cod_limpo = re.sub(r'\D', '', str(cod_fam_planilha)).strip()
            fila.put({"tipo": "log", "msg": f"   -> Atualizando Código Familiar para: {cod_limpo}...\n"})

            campo_cod = modal_fam.locator('text="Código familiar"').locator('xpath=following-sibling::input | ../following-sibling::*//input | following::input[1]').first
            if not campo_cod.is_visible():
                campo_cod = modal_fam.locator('input[name*="codigo_familiar"], input[id*="codigo_familiar"]').first

            if campo_cod.is_visible():
                campo_cod.click()
                campo_cod.press("Control+A")
                campo_cod.press("Backspace")
                campo_cod.type(cod_limpo, delay=30)
                page.wait_for_timeout(200)

        # 7.2. Telefone Residencial
        campo_tel = modal_fam.locator('text="Telefone Residencial"').locator('xpath=following-sibling::input | ../following-sibling::*//input | following::input[1]').first
        if not campo_tel.is_visible():
            campo_tel = modal_fam.locator('input[name*="telefone"], input[id*="telefone"]').first

        if campo_tel.is_visible():
            campo_tel.click()
            campo_tel.press("Control+A")
            campo_tel.press("Backspace")
            page.wait_for_timeout(200)

        # 7.3. Forma de Acesso: "Por demanda espontânea"
        select_demanda = modal_fam.locator('select:has-text("demanda"), select[name*="demanda"], select[id*="demanda"]').first
        if not select_demanda.is_visible():
            select_demanda = modal_fam.locator('text="De que forma a família"').locator('xpath=following::select[1]').first

        if select_demanda.is_visible():
            select_demanda.focus()
            try:
                select_demanda.select_option(label="Por demanda espontânea")
            except Exception:
                select_demanda.select_option(label=re.compile(r"demanda espontânea", re.IGNORECASE))
            select_demanda.dispatch_event("change")
            select_demanda.dispatch_event("input")
            page.wait_for_timeout(300)

        # 7.4. Confirmar 'OK' na janela modal
        btn_ok_fam = modal_fam.locator('button:visible:has-text("OK"), .ui-dialog-buttonpane button:has-text("OK")').first
        if btn_ok_fam.is_visible():
            btn_ok_fam.click()
            page.wait_for_timeout(1500)

    # 8. Encerrar Atendimento e marcar Cadastramento/Atualização
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

    # 9. Retorno ao painel de busca pelo botão '<'
    btn_seta_voltar = page.locator('button:has-text("Agendar Atendimento"), a:has-text("Agendar Atendimento")').locator('xpath=preceding-sibling::*[1]').first
    if btn_seta_voltar.is_visible():
        btn_seta_voltar.click()
    page.wait_for_timeout(1000)

    return obs_membro


def processar_automacao(caminho_planilha, pasta_destino_base, nome_aba, evento_login_pronto, fila, cancel_event):
    """Orquestrador principal chamado pela interface SuiteGesuasApp."""
    try:
        fila.put({"tipo": "log", "msg": f"[MOTOR GESUAS_BOT]: Iniciando rotina de lançamentos.\n"})
        fila.put({"tipo": "log", "msg": f" -> Planilha: {os.path.basename(caminho_planilha)} [Aba: {nome_aba}]\n"})

        pasta_planilhas = os.path.join(pasta_destino_base, "PLANILHAS_EXCEL")
        pasta_relatorios = os.path.join(pasta_destino_base, "RELATORIOS_PDF")
        pasta_checkpoints = os.path.join(pasta_destino_base, "CHECKPOINTS")
        for p in [pasta_planilhas, pasta_relatorios, pasta_checkpoints]:
            os.makedirs(p, exist_ok=True)

        arquivo_excel = pd.ExcelFile(caminho_planilha)
        todas_abas = arquivo_excel.sheet_names

        if nome_aba not in todas_abas:
            fila.put({"tipo": "log", "msg": f"[ERRO]: Aba '{nome_aba}' não encontrada na planilha.\n"})
            fila.put({"tipo": "fim_robo", "sucesso": False})
            return

        df = pd.read_excel(caminho_planilha, sheet_name=nome_aba)

        col_nome = next((c for c in df.columns if "NOME" in str(c).upper()), "NOME")
        col_cpf = next((c for c in df.columns if "CPF" in str(c).upper()), "CPF")
        col_cod_fam = next((c for c in df.columns if "COD" in str(c).upper() or "FAMILIAR" in str(c).upper()), "COD FAMILIAR")
        col_servico = next((c for c in df.columns if "SERVI" in str(c).upper()), "SERVICO")
        col_data = next((c for c in df.columns if "DATA" in str(c).upper()), "DATA")
        col_hora = next((c for c in df.columns if "HORA" in str(c).upper()), "HORAS")
        col_gesuas = next((c for c in df.columns if "GESUAS" in str(c).upper()), "GESUAS")
        col_obs_orig = next((c for c in df.columns if "OBS" in str(c).upper() or "VISITA" in str(c).upper()), None)

        total_linhas = len(df)
        fila.put({"tipo": "log", "msg": f"[PLANILHA] {total_linhas} linhas mapeadas na aba {nome_aba}.\n"})

        fila.put({"tipo": "log", "msg": "[EDGE] Inicializando Microsoft Edge na porta 9222...\n"})
        iniciar_edge()

        fila.put({
            "tipo": "aguardar_login",
            "msg": "Faça login no painel inicial do GESUAS e clique em '2. Confirmar Login GESUAS (Iniciar Robô)' para começar.\n"
        })

        while not evento_login_pronto.is_set():
            if cancel_event.is_set():
                fila.put({"tipo": "cancelado"})
                return
            time.sleep(0.3)

        fila.put({"tipo": "log", "msg": "\n[GESUAS] Conexão confirmada via Playwright CDP...\n"})

        resultados_robo = []
        alteracoes_feitas = False

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            page = conectar_pagina_gesuas(browser)

            for idx, linha in df.iterrows():
                if cancel_event.is_set():
                    fila.put({"tipo": "cancelado"})
                    break

                num_linha = idx + 1
                progresso_atual = num_linha / total_linhas

                def notificar_progresso(msg_extra=""):
                    fila.put({
                        "tipo": "progresso",
                        "val": progresso_atual,
                        "msg": msg_extra
                    })

                nome_municipe = str(linha.get(col_nome, '')).strip()

                if not nome_municipe or nome_municipe.lower() in ['nan', 'none', '']:
                    notificar_progresso()
                    continue

                cpf_raw = str(linha.get(col_cpf, '')).strip()
                cod_fam_planilha = str(linha.get(col_cod_fam, '')).strip()
                servico = str(linha.get(col_servico, '')).strip().upper()
                
                data_atend = formatar_data_segura(linha.get(col_data, ''))
                hora_atend = formatar_hora_segura(linha.get(col_hora, ''))
                
                obs_planilha = str(linha.get(col_obs_orig, '')).strip() if col_obs_orig else ""
                if obs_planilha.lower() in ['nan', 'none']:
                    obs_planilha = ""

                if not data_atend or not servico or servico in ['NAN', 'NONE']:
                    fila.put({"tipo": "log", "msg": f"\n[{num_linha}/{total_linhas}] Linha {num_linha}: Dados incompletos. A ignorar...\n"})
                    notificar_progresso()
                    continue

                data_hora_str = f"{data_atend} {hora_atend}".strip()
                status_gesuas_atual = str(linha.get(col_gesuas, '')).strip().upper()

                fila.put({"tipo": "log", "msg": f"\n[{num_linha}/{total_linhas}] Linha {num_linha}: {nome_municipe}\n"})
                fila.put({"tipo": "log", "msg": f" -> CPF: {cpf_raw} | Serviço: {servico} | Data: {data_hora_str}\n"})

                # REGRA 1: Já marcado com OK
                if "OK" in status_gesuas_atual:
                    fila.put({"tipo": "log", "msg": " -> [PULADO]: Atendimento já sinalizado como 'OK' na planilha.\n"})
                    resultados_robo.append({
                        "Linha": num_linha,
                        "Nome": nome_municipe,
                        "CPF": cpf_raw,
                        "Data": data_atend,
                        "Hora": hora_atend,
                        "Serviço": servico,
                        "Cód. Familiar Planilha": cod_fam_planilha,
                        "Status Robô": "JÁ CADASTRADO",
                        "Diagnóstico": obs_planilha if obs_planilha else "Registro prévio existente"
                    })
                    notificar_progresso()
                    continue

                # REGRA 2: CONSULTA (não gera atendimento)
                if "CONSULTA" in servico:
                    fila.put({"tipo": "log", "msg": " -> [CONSULTA]: Apenas verificação cadastral. Não gera atendimento.\n"})
                    df.at[idx, col_gesuas] = "OK (CONSULTA)"
                    alteracoes_feitas = True
                    resultados_robo.append({
                        "Linha": num_linha,
                        "Nome": nome_municipe,
                        "CPF": cpf_raw,
                        "Data": data_atend,
                        "Hora": hora_atend,
                        "Serviço": "CONSULTA",
                        "Cód. Familiar Planilha": cod_fam_planilha,
                        "Status Robô": "CONSULTA",
                        "Diagnóstico": obs_planilha if obs_planilha else "Informativo - sem alteração de cadastro"
                    })
                    notificar_progresso()
                    continue

                # 1. Pesquisa do munícipe
                achou = buscar_municipe(page, nome_municipe, cpf_raw, fila)
                if not achou:
                    fila.put({"tipo": "log", "msg": f" -> [NÃO LOCALIZADO]: Munícipe não encontrado no GESUAS.\n"})
                    resultados_robo.append({
                        "Linha": num_linha,
                        "Nome": nome_municipe,
                        "CPF": cpf_raw,
                        "Data": data_atend,
                        "Hora": hora_atend,
                        "Serviço": servico,
                        "Cód. Familiar Planilha": cod_fam_planilha,
                        "Status Robô": "NÃO LOCALIZADO",
                        "Diagnóstico": obs_planilha if obs_planilha else "Cadastrar pessoa/família no GESUAS"
                    })
                    notificar_progresso()
                    continue

                # 2. Verificação de Pessoa Desligada
                status_acesso = verificar_pessoa_desligada_ou_acessar_familia(page, nome_municipe, fila)
                if status_acesso == "DESLIGADA":
                    retornar_para_busca(page)
                    resultados_robo.append({
                        "Linha": num_linha,
                        "Nome": nome_municipe,
                        "CPF": cpf_raw,
                        "Data": data_atend,
                        "Hora": hora_atend,
                        "Serviço": servico,
                        "Cód. Familiar Planilha": cod_fam_planilha,
                        "Status Robô": "DESLIGADA",
                        "Diagnóstico": obs_planilha if obs_planilha else "Munícipe consta como desligado no sistema"
                    })
                    notificar_progresso()
                    continue

                # 3. Verificação de duplicidade em 'Editar um Atendimento'
                ja_tem = checar_duplicidade_atendimento(page, data_hora_str, data_atend, hora_atend, fila)
                if ja_tem:
                    df.at[idx, col_gesuas] = "OK"
                    alteracoes_feitas = True
                    resultados_robo.append({
                        "Linha": num_linha,
                        "Nome": nome_municipe,
                        "CPF": cpf_raw,
                        "Data": data_atend,
                        "Hora": hora_atend,
                        "Serviço": servico,
                        "Cód. Familiar Planilha": cod_fam_planilha,
                        "Status Robô": "JÁ CADASTRADO",
                        "Diagnóstico": obs_planilha if obs_planilha else f"Atendimento já existente em {data_hora_str}"
                    })
                    notificar_progresso()
                    continue

                # 4. Lançamento e encerramento
                fila.put({"tipo": "log", "msg": f" -> [LANÇAMENTO]: A registrar atendimento de {servico} ({data_hora_str})...\n"})
                obs_membro = registrar_atendimento_completo(page, data_hora_str, nome_municipe, cod_fam_planilha, fila)

                df.at[idx, col_gesuas] = "OK"
                alteracoes_feitas = True
                fila.put({"tipo": "log", "msg": f" -> [SUCESSO]: Atendimento registrado e encerrado no GESUAS com sucesso!\n"})

                diag_final = f"{obs_planilha} {obs_membro}".strip() if (obs_planilha or obs_membro) else "Atendimento lançado no GESUAS"

                resultados_robo.append({
                    "Linha": num_linha,
                    "Nome": nome_municipe,
                    "CPF": cpf_raw,
                    "Data": data_atend,
                    "Hora": hora_atend,
                    "Serviço": servico,
                    "Cód. Familiar Planilha": cod_fam_planilha,
                    "Status Robô": "SUCESSO",
                    "Diagnóstico": diag_final
                })

                notificar_progresso(f" -> [{num_linha}/{total_linhas}] Concluído: {nome_municipe}\n")

        # =========================================================================
        # GRAVAÇÃO DA CÓPIA ATUALIZADA DA PLANILHA E DOS RELATÓRIOS (EXCEL E PDF)
        # =========================================================================
        carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_base = f"Relatorio_Robo_Lancamentos_{nome_aba}_{carimbo}"

        # 1. Cópia completa da planilha com 'OK' na aba trabalhada
        if alteracoes_feitas:
            nome_copia = f"CADASTRO_ATUALIZADO_{nome_aba}_{carimbo}.xlsx"
            caminho_copia = os.path.join(pasta_planilhas, nome_copia)
            try:
                with pd.ExcelWriter(caminho_copia, engine="openpyxl") as writer:
                    for aba in todas_abas:
                        if aba == nome_aba:
                            df.to_excel(writer, sheet_name=aba, index=False)
                        else:
                            df_outra = pd.read_excel(caminho_planilha, sheet_name=aba)
                            df_outra.to_excel(writer, sheet_name=str(aba), index=False)

                fila.put({"tipo": "log", "msg": f"\n[COPIA CRIADA] Cópia atualizada gravada em PLANILHAS_EXCEL:\n -> {nome_copia}\n"})
                fila.put({"tipo": "log", "msg": "[ORIGINAL PRESERVADA] A planilha bruta de entrada permaneceu intacta.\n"})
            except Exception as e_salvar:
                fila.put({"tipo": "log", "msg": f"[AVISO COPIA]: Falha ao gerar cópia: {str(e_salvar)}\n"})

        # 2. Gravação da Planilha Excel com o log analítico do Robô
        if resultados_robo:
            caminho_relatorio = os.path.join(pasta_planilhas, f"{nome_base}.xlsx")
            pd.DataFrame(resultados_robo).to_excel(caminho_relatorio, index=False)
            fila.put({"tipo": "log", "msg": f"[RELATÓRIO EXECUÇÃO] Gravado em PLANILHAS_EXCEL:\n -> {os.path.basename(caminho_relatorio)}\n"})

            # 3. Compilação do Relatório Oficial em PDF (relatorio_pdf.py)
            caminho_pdf_final = os.path.join(pasta_relatorios, f"{nome_base}.pdf")
            try:
                fila.put({"tipo": "log", "msg": "[GERADOR PDF] Compilando relatório oficial em PDF com legenda e estilos...\n"})
                
                dados_para_pdf = []
                for r in resultados_robo:
                    dados_para_pdf.append({
                        "ID": r.get("Linha", ""),
                        "Nome": r.get("Nome", ""),
                        "CPF": r.get("CPF", ""),
                        "Data": r.get("Data", ""),
                        "Hora": r.get("Hora", ""),
                        "TipoAcao": r.get("Serviço", "ATUALIZAÇÃO"),
                        "Status": r.get("Status Robô", ""),
                        "Obs": r.get("Diagnóstico", "")
                    })

                relatorio_pdf.gerar_relatorio_pdf(
                    dados_para_pdf,
                    nome_aba,
                    caminho_pdf_final
                )

                if os.path.exists(caminho_pdf_final):
                    fila.put({"tipo": "log", "msg": f"[NOVO ARQUIVO PDF] Gravado em RELATORIOS_PDF:\n -> {os.path.basename(caminho_pdf_final)}\n"})
                else:
                    fila.put({"tipo": "log", "msg": "[AVISO PDF]: Arquivo PDF não localizado após o processo de compilação.\n"})
            except Exception as e_pdf:
                fila.put({"tipo": "log", "msg": f"[ERRO NO GERADOR PDF]: Falha ao gerar PDF: {str(e_pdf)}\n"})

        fila.put({"tipo": "log", "msg": f"\n[FINALIZADO] Operação do Robô de Lançamentos finalizada com êxito!\n"})
        fila.put({"tipo": "fim_robo", "sucesso": True, "pasta_destino": pasta_destino_base})

    except Exception as erro:
        fila.put({"tipo": "log", "msg": f"\n[ERRO CRÍTICO NA AUTOMAÇÃO]: {str(erro)}\n"})
        fila.put({"tipo": "fim_robo", "sucesso": False})
        