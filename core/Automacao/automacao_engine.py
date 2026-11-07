# -*- coding: utf-8 -*-
"""
========================================================================================
SUITE GESUAS - CENTRAL DE OPERAÇÕES INTEGRADA (CRAS SUL - CAMPO BELO / MG)
MÓDULO: MOTOR DE AUTOMAÇÃO WEB PLAYWRIGHT (automacao_engine.py)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Orquestra o pipeline de lançamentos da Suite GESUAS com:
            - Tipagem blindada contra falhas de float64 em colunas vazias;
            - Tratamento para consultas sem código familiar (ex: excluídos / orientações);
            - Política de não-regressão cadastral (preserva código mais recente existente);
            - Tratamento ativo de modal de código duplicado com descarte gracioso;
            - Encerramento cirúrgico com a 3ª opção isolada por índice direto;
            - Gravação de checkboxes via botão 'Iniciar' na edição de atendimento;
            - Saneamento cadastral compulsório em 'Editar família';
            - Retorno confiável à sanfona 'Buscar pessoa' e blindagem anti-overlay.
========================================================================================
"""

import os
import sys
import re
import time
import subprocess
import unicodedata
from datetime import datetime, date, time as datetime_time
import pandas as pd
from playwright.sync_api import sync_playwright

DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_ATUAL not in sys.path:
    sys.path.insert(0, DIRETORIO_ATUAL)

import relatorio_pdf


def normalizar_texto(texto: str) -> str:
    """Remove acentuações e caracteres especiais, retornando texto em caixa alta."""
    if not texto or not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return re.sub(r'\s+', ' ', texto).strip().upper()


def eh_servico_visita_domiciliar(servico_raw: str, obs_raw: str = "") -> bool:
    """Detecta se há menção a visita/entrevista domiciliar no serviço ou na observação."""
    texto_combinado = f"{normalizar_texto(servico_raw)} {normalizar_texto(obs_raw)}"
    termos = ["VISITA", "DOMICILI", "DOMICILIO", "EM DOMICILIO", "ENTREVISTA DOMICILIAR"]
    return any(termo in texto_combinado for termo in termos)


def formatar_data_segura(valor) -> str:
    """Converte valores de data da planilha para DD/MM/AAAA."""
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
    """Converte valores de hora da planilha para HH:MM."""
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
    """Localiza a aba ativa do GESUAS."""
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
    """Fecha janelas modais de erro de busca."""
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


def fechar_todas_modais_ativas(page):
    """Fecha todas as modais do jQuery UI e remove overlays bloqueadores via JS."""
    try:
        page.evaluate("""() => {
            const modais = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
            for (const m of modais) {
                const btnX = m.querySelector('.ui-dialog-titlebar-close');
                if (btnX) btnX.click();
            }
            const overlays = Array.from(document.querySelectorAll('.ui-widget-overlay, .loading-mask'));
            for (const o of overlays) {
                o.remove();
            }
        }""")
        page.wait_for_timeout(400)
    except Exception:
        pass


def retornar_para_busca(page):
    """Retorna ao painel de busca clicando no botão '<' ou na aba 'Buscar pessoa'."""
    fechar_todas_modais_ativas(page)
    try:
        btn_seta_voltar = page.locator('button:has-text("Agendar Atendimento"), a:has-text("Agendar Atendimento")').locator('xpath=preceding-sibling::*[1]').first
        if not btn_seta_voltar.is_visible():
            btn_seta_voltar = page.locator('a:visible:has-text("<"), button:visible:has-text("<")').first
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
    """Executa a busca por CPF (11 dígitos) com fallback por Nome."""
    retornar_para_busca(page)
    campo_cpf = page.locator('#pessoa_search_cpf')

    cpf_digitos = re.sub(r'\D', '', str(cpf)) if cpf and str(cpf).lower() not in ['nan', 'none', 'nat'] else ""
    achou_resultado = False

    if len(cpf_digitos) == 11:
        campo_cpf.wait_for(state="visible", timeout=5000)
        campo_cpf.click()
        campo_cpf.fill(cpf_digitos)
        page.locator('#btn_procurar, button:has-text("Procurar..."), a:has-text("Procurar...")').first.click()
        page.wait_for_timeout(1500)
        fechar_modal_erro_busca(page)

        if not page.locator('text="Não foram encontradas pessoas"').is_visible() and page.locator('text="Pessoas encontradas"').is_visible():
            achou_resultado = True

    if not achou_resultado:
        fila.put({"tipo": "log", "msg": f"   [!] CPF não localizou. Buscando por Nome: {nome}...\n"})
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
    """Verifica desligamento ou múltiplos cadastros e acessa a tela da família."""
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
        fila.put({"tipo": "log", "msg": f"   [AVISO] Múltiplos cadastros para '{nome}'. Acesse a família no Edge se necessário.\n"})
        page.wait_for_timeout(1500)
    
    btn_boneco = page.locator('a[title*="Ver cadastro da família"], button[title*="Ver cadastro da família"]').first
    if not btn_boneco.is_visible():
        btn_boneco = page.locator('#pessoasListDiv .ui-button, #pessoasListDiv button, #pessoasListDiv a').first
    btn_boneco.click(force=True)
    page.wait_for_timeout(2000)

    return "OK"


def verificar_titularidade_rf(page, cpf_municipe, nome_municipe) -> tuple[bool, str]:
    """Valida se o munícipe é o Responsável Familiar (RF) da composição exibida."""
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
    cpf_limpo = re.sub(r'\D', '', str(cpf_municipe))
    eh_rf = False

    if len(cpf_limpo) == 11:
        try:
            eh_rf = page.evaluate("""(cpfAlvo) => {
                const linhas = Array.from(document.querySelectorAll('table tr'));
                for (const tr of linhas) {
                    if (tr.innerText.includes('Pessoa de referência') && tr.innerText.replace(/\\D/g, '').includes(cpfAlvo)) {
                        return true;
                    }
                }
                return false;
            }""", cpf_limpo)
        except Exception:
            eh_rf = False

    if not eh_rf and nome_rf_tela:
        partes_nome = nome_municipe.strip().upper().split()
        chave = f"{partes_nome[0]} {partes_nome[1]}" if len(partes_nome) > 1 else partes_nome[0]
        eh_rf = chave in nome_rf_tela.upper()

    return eh_rf, nome_rf_tela


def obter_codigo_familiar_tela(page) -> str:
    """Extrai rigorosamente os 11 dígitos que sucedem o termo 'Cód. familiar:' na tela."""
    try:
        texto_tela = page.evaluate("""() => document.body.innerText""")
        m = re.search(r'C[oó]d(?:igo)?\.?\s*familiar[^\d\n\r]*(\d{11})', texto_tela, re.IGNORECASE)
        if m:
            return m.group(1)
        return ""
    except Exception:
        return ""


def aplicar_saneamento_editar_familia(page, cod_fam, eh_visita_rf: bool, fila):
    """
    Acessa 'Editar família' (botão abaixo à esquerda) para sanear:
    1. Código Familiar: só preenche se o campo na tela estiver vazio ou incompleto.
       Se já possuir 11 dígitos (atendimento consolidado), preserva o existente.
    2. Limpa telefones residenciais e celulares obsoletos.
    3. Define a Forma de Acesso.
    4. Trata alertas de duplicidade de código sem reter a camada de overlay.
    """
    fechar_todas_modais_ativas(page)
    fila.put({"tipo": "log", "msg": " -> Acessando 'Editar família' (abaixo à esquerda) para saneamento...\n"})
    
    btn_editar_fam = page.locator('button:visible:has-text("Editar família"), a:visible:has-text("Editar família")').first
    try:
        btn_editar_fam.wait_for(state="visible", timeout=6000)
        btn_editar_fam.click()
        page.wait_for_timeout(1200)
    except Exception:
        fila.put({"tipo": "log", "msg": "   [AVISO]: Botão 'Editar família' não clicável.\n"})
        return

    modal_fam = page.locator('.ui-dialog:visible:has-text("Editar família"), div[role="dialog"]:visible:has-text("Editar família")').last
    try:
        modal_fam.wait_for(state="visible", timeout=5000)
    except Exception:
        fechar_todas_modais_ativas(page)
        return

    # 1. Localização e Verificação de Não-Regressão do Código Familiar
    campo_cod = modal_fam.locator('text="Código familiar"').locator('xpath=following-sibling::input | ../following-sibling::*//input | following::input[1]').first
    if not campo_cod.is_visible():
        campo_cod = modal_fam.locator('input[name*="codigo_familiar"], input[id*="codigo_familiar"]').first

    if campo_cod.is_visible():
        valor_atual_tela = re.sub(r'\D', '', str(campo_cod.input_value() or "")).strip()
        cod_limpo_planilha = re.sub(r'\D', '', str(cod_fam)).strip() if cod_fam and str(cod_fam).lower() not in ['nan', 'none'] else ""

        if len(valor_atual_tela) == 11:
            fila.put({"tipo": "log", "msg": f"   -> [PRESERVADO]: Família já possui Código ({valor_atual_tela}) no GESUAS. Mantendo mais recente.\n"})
        elif len(cod_limpo_planilha) == 11:
            fila.put({"tipo": "log", "msg": f"   -> Atualizando Código Familiar para: {cod_limpo_planilha}...\n"})
            campo_cod.click()
            campo_cod.press("Control+A")
            campo_cod.press("Backspace")
            campo_cod.type(cod_limpo_planilha, delay=25)
            page.wait_for_timeout(150)

    # 2. Limpeza de Telefones Legados
    fila.put({"tipo": "log", "msg": "   -> Limpando campo de telefone residencial / celular...\n"})
    page.evaluate("""() => {
        const dialog = Array.from(document.querySelectorAll('.ui-dialog, div[role="dialog"]'))
                            .find(d => d.innerText.includes('Editar família'));
        if (!dialog) return;
        const inputs = Array.from(dialog.querySelectorAll('input[type="text"]'));
        inputs.forEach(inp => {
            const rotulo = (inp.closest('tr, div') ? inp.closest('tr, div').innerText : '').toUpperCase();
            if (rotulo.includes('TELEFONE') || rotulo.includes('CELULAR')) {
                inp.value = '';
                inp.dispatchEvent(new Event('change', { bubbles: true }));
                inp.dispatchEvent(new Event('input', { bubbles: true }));
            }
        });
    }""")
    page.wait_for_timeout(200)

    # 3. Forma de Acesso
    termo_acesso = "Busca Ativa realizada pela equipe da unidade" if eh_visita_rf else "Por demanda espontânea"
    fila.put({"tipo": "log", "msg": f"   -> Forma de Acesso configurada para: '{termo_acesso}'\n"})
    page.evaluate("""(opcaoDesejada) => {
        const selects = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"]) select'));
        for (const sel of selects) {
            for (const opt of sel.options) {
                if (opt.text.toUpperCase().includes(opcaoDesejada.toUpperCase())) {
                    sel.value = opt.value;
                    sel.dispatchEvent(new Event('change', { bubbles: true }));
                    return;
                }
            }
        }
    }""", termo_acesso)
    page.wait_for_timeout(300)

    # 4. Gravação da Modal e Tratamento de Alerta de Duplicidade
    btn_ok = modal_fam.locator('button:visible:has-text("OK"), .ui-dialog-buttonpane button:has-text("OK")').first
    if btn_ok.is_visible():
        btn_ok.click()
        page.wait_for_timeout(1000)

        tratou_alerta = page.evaluate("""() => {
            const dialogs = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
            const alertModal = dialogs.find(d => 
                d.innerText.toLowerCase().includes('já cadastrado') || 
                d.innerText.toLowerCase().includes('código familiar já') ||
                d.innerText.toLowerCase().includes('erro ao')
            );
            if (alertModal) {
                const btnOkAlerta = alertModal.querySelector('button, .ui-button');
                if (btnOkAlerta) btnOkAlerta.click();
                return true;
            }
            return false;
        }""")

        if tratou_alerta:
            fila.put({"tipo": "log", "msg": "   [AVISO DUPLICIDADE]: Código já existente em outro cadastro. Cancelando edição...\n"})
            page.wait_for_timeout(600)
            btn_canc = modal_fam.locator('button:visible:has-text("Cancelar"), .ui-dialog-titlebar-close').first
            if btn_canc.is_visible():
                btn_canc.click()
                page.wait_for_timeout(600)

    # 5. Sincronização explícita: aguarda o diálogo e os overlays saírem da tela
    try:
        modal_fam.wait_for(state="hidden", timeout=4000)
    except Exception:
        pass

    fechar_todas_modais_ativas(page)
    page.wait_for_timeout(500)


def encerrar_atendimento_ativo(page, fila):
    """
    Encerra o atendimento aberto:
    1. Clica no botão 'Encerrar atendimento'.
    2. Itera diretamente pela lista de checkboxes: desmarca todos exceto o 3º (índice 2).
    3. Clica no botão OK da barra inferior.
    """
    fechar_todas_modais_ativas(page)

    btn_encerrar = page.locator('a:has-text("Encerrar atendimento"), button:has-text("Encerrar atendimento")').first
    try:
        btn_encerrar.wait_for(state="visible", timeout=6000)
    except Exception:
        return

    fila.put({"tipo": "log", "msg": " -> Abrindo modal 'Encerrar atendimento'...\n"})
    btn_encerrar.click(force=True)
    page.wait_for_timeout(1500)

    fechou_ok = page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
        const modal = dialogs.find(d => d.innerText.includes('Encerrar Atendimento') || d.innerText.includes('Tipos'));
        if (!modal) return false;

        const checkboxes = Array.from(modal.querySelectorAll('input[type="checkbox"]'));
        
        checkboxes.forEach((chk, index) => {
            if (index === 2) {
                if (!chk.checked) chk.click();
                chk.checked = true;
            } else {
                if (chk.checked) chk.click();
                chk.checked = false;
            }
            chk.dispatchEvent(new Event('change', { bubbles: true }));
        });

        const botoes = Array.from(modal.querySelectorAll('.ui-dialog-buttonpane button, button'));
        const btnOk = botoes.find(b => b.innerText.trim().toUpperCase() === 'OK');
        if (btnOk) {
            btnOk.click();
            return true;
        }
        return false;
    }""")

    page.wait_for_timeout(1500)
    if not fechou_ok:
        btn_ok_pane = page.locator('.ui-dialog:visible:has-text("Encerrar Atendimento") .ui-dialog-buttonpane button:has-text("OK")').first
        if btn_ok_pane.is_visible():
            btn_ok_pane.click()
            page.wait_for_timeout(1500)

    fechar_todas_modais_ativas(page)


def sanear_consulta_ultimo_atendimento(page, cod_fam_planilha, fila) -> str:
    """
    Exclusivo para CONSULTA realizada pelo RF:
    1. Compara o Código Familiar da tela com o da planilha.
    2. Se faltar/divergir: abre histórico, reabre o mais recente via 'Iniciar',
       saneia em 'Editar família', encerra com 'Cadastramento/Atualização' e volta para a busca.
    """
    cod_planilha_limpo = re.sub(r'\D', '', str(cod_fam_planilha)).strip()
    cod_tela_limpo = obter_codigo_familiar_tela(page)

    if cod_tela_limpo and cod_tela_limpo == cod_planilha_limpo:
        fila.put({"tipo": "log", "msg": f"   -> [CONSULTA]: Código Familiar ({cod_tela_limpo}) coincide com a planilha. Sem alterações.\n"})
        retornar_para_busca(page)
        return "Consulta - Código já atualizado"

    fila.put({"tipo": "log", "msg": f"   -> [DIVERGÊNCIA/AUSÊNCIA]: Código no GESUAS ('{cod_tela_limpo}') difere da planilha ('{cod_planilha_limpo}').\n"})
    fila.put({"tipo": "log", "msg": "   -> Acessando histórico em 'Editar um Atendimento' para vincular alteração...\n"})

    btn_editar = page.locator('button:visible:has-text("Editar um Atendimento"), a:visible:has-text("Editar um Atendimento")').first
    try:
        btn_editar.wait_for(state="visible", timeout=6000)
    except Exception:
        retornar_para_busca(page)
        return "Consulta (Histórico indisponível)"

    btn_editar.click()
    page.wait_for_timeout(1800)

    abriu_edicao = page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
        for (const d of dialogs) {
            const btnEd = d.querySelector('a, button, .ui-icon-pencil');
            if (btnEd && (btnEd.innerText.toUpperCase().includes('EDITAR') || (btnEd.title && btnEd.title.toLowerCase().includes('editar')) || btnEd.className.includes('ui-icon-pencil'))) {
                btnEd.click();
                return true;
            }
        }
        return false;
    }""")

    page.wait_for_timeout(1500)

    if not abriu_edicao:
        fila.put({"tipo": "log", "msg": "   -> [CONSULTA]: Família sem atendimentos anteriores registrados. Desconsiderando saneamento...\n"})
        fechar_todas_modais_ativas(page)
        retornar_para_busca(page)
        return "Consulta mantida (Sem atendimentos anteriores)"

    fila.put({"tipo": "log", "msg": "   -> Reabrindo último atendimento via botão 'Iniciar'...\n"})
    page.evaluate("""() => {
        const modais = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
        for (const m of modais) {
            const btnIniciar = Array.from(m.querySelectorAll('button, a')).find(b => b.innerText.trim().toUpperCase() === 'INICIAR');
            if (btnIniciar) {
                btnIniciar.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(1800)
    fechar_todas_modais_ativas(page)

    aplicar_saneamento_editar_familia(page, cod_planilha_limpo, eh_visita_rf=False, fila=fila)
    encerrar_atendimento_ativo(page, fila)
    retornar_para_busca(page)

    return "Consulta - Código Familiar saneado no último atendimento"


def checar_duplicidade_e_adequar_visita(page, data_hora_str, data_atend, hora_atend, eh_visita_rf: bool, cod_fam: str, fila=None) -> tuple[bool, str]:
    """
    Verifica se o atendimento já consta no histórico de 'Editar um Atendimento'.
    Se for Visita Domiciliar pré-existente com RF:
      - Clica em 'Editar' na linha correspondente;
      - Marca 'Visita Domiciliar' e 'Busca Ativa' e grava no botão 'Iniciar';
      - Saneia a família e encerra na 3ª opção.
    Garante que qualquer modal ou overlay remanescente seja fechado compulsoriamente.
    """
    def log(msg):
        if fila:
            fila.put({"tipo": "log", "msg": msg})
        else:
            print(msg.strip())

    fechar_todas_modais_ativas(page)

    btn_editar = page.locator('button:visible:has-text("Editar um Atendimento"), a:visible:has-text("Editar um Atendimento")').first
    try:
        btn_editar.wait_for(state="visible", timeout=6000)
        btn_editar.click()
    except Exception:
        fechar_todas_modais_ativas(page)
        return False, ""

    page.wait_for_timeout(1500)

    dados_historico = page.evaluate("""(args) => {
        const [dataBusca, horaBusca] = args;
        const dialogs = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
        const modal = dialogs.find(d => d.innerText.includes('Editar Atendimento') || d.innerText.includes('Data do atendimento'));
        if (!modal) return { existe: false, texto: '' };

        const texto = modal.innerText.replace(/\\s+/g, ' ');
        const achouData = texto.includes(dataBusca);
        const achouHora = horaBusca ? texto.includes(horaBusca) : true;

        return {
            existe: achouData && achouHora,
            texto: texto
        };
    }""", [data_atend, hora_atend])

    ja_cadastrado = dados_historico["existe"]
    diag_visita = ""

    if ja_cadastrado:
        log(f"   -> [HISTÓRICO LOCALIZADO]: Atendimento de {data_hora_str} encontrado no histórico.\n")
        
        page.evaluate("""(dataAlvo) => {
            const dialogs = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
            const modal = dialogs.find(d => d.innerText.includes('Editar Atendimento') || d.innerText.includes('Data do atendimento'));
            if (!modal) return false;

            const linhas = Array.from(modal.querySelectorAll('tr, div, li, .ui-widget-content'));
            for (const lin of linhas) {
                if (lin.innerText && lin.innerText.includes(dataAlvo)) {
                    const btn = lin.querySelector('button, a, .ui-button');
                    if (btn) {
                        btn.click();
                        return true;
                    }
                }
            }
            const botoes = Array.from(modal.querySelectorAll('button, a')).filter(b => b.innerText.includes('Editar'));
            if (botoes.length > 0) {
                botoes[0].click();
                return true;
            }
            return false;
        }""", data_atend)

        page.wait_for_timeout(1800)

        if eh_visita_rf:
            log("   -> Marcando checkboxes 'Visita Domiciliar' e 'Busca Ativa'...\n")
            page.evaluate("""() => {
                const modais = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
                for (const modal of modais) {
                    const checkboxes = Array.from(modal.querySelectorAll('input[type="checkbox"]'));
                    checkboxes.forEach(chk => {
                        const rotulo = (chk.closest('tr, td, label, div') ? chk.closest('tr, td, label, div').innerText : '').toUpperCase();
                        if (rotulo.includes('VISITA DOMICILIAR') || rotulo.includes('BUSCA ATIVA')) {
                            if (!chk.checked) chk.click();
                        }
                    });
                }
            }""")
            page.wait_for_timeout(500)

            log("   -> Gravando edição do atendimento no botão 'Iniciar'...\n")
            page.evaluate("""() => {
                const modais = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
                for (const m of modais) {
                    const btnIniciar = Array.from(m.querySelectorAll('button, a')).find(b => b.innerText.trim().toUpperCase() === 'INICIAR');
                    if (btnIniciar) {
                        btnIniciar.click();
                        return;
                    }
                }
            }""")
            page.wait_for_timeout(2000)
            fechar_todas_modais_ativas(page)

            aplicar_saneamento_editar_familia(page, cod_fam, eh_visita_rf=True, fila=fila)
            encerrar_atendimento_ativo(page, fila)
            diag_visita = "Visita Domiciliar editada e confirmada no GESUAS"

        else:
            log("   -> Atendimento comum já existente. Fechando histórico...\n")
            fechar_todas_modais_ativas(page)
            diag_visita = "Atendimento comum existente (Auditado)"

        retornar_para_busca(page)
        return True, diag_visita

    fechar_todas_modais_ativas(page)
    page.wait_for_timeout(500)
    return False, ""


def registrar_atendimento_completo(page, data_hora_str, nome, cod_fam_planilha, servico_planilha, obs_planilha, cpf_municipe, fila):
    """Executa o ciclo completo de lançamento novo (incluindo INCLUSAO e ATUALIZACAO)."""
    fechar_todas_modais_ativas(page)

    eh_visita = eh_servico_visita_domiciliar(servico_planilha, obs_planilha)
    eh_rf, nome_rf_tela = verificar_titularidade_rf(page, cpf_municipe, nome)
    eh_visita_rf = eh_visita and eh_rf

    btn_iniciar_tela = page.locator('button:visible:has-text("Iniciar atendimento"), a:visible:has-text("Iniciar atendimento")').filter(has_not=page.locator('#btnNovaFamiliaIniciarAtendimento')).first
    btn_iniciar_tela.wait_for(state="visible", timeout=7000)
    btn_iniciar_tela.click(force=True)
    page.wait_for_timeout(1000)

    modal_conteudo = page.locator('#_iniciarAtendimento')
    modal_conteudo.wait_for(state="visible", timeout=10000)
    page.wait_for_timeout(500)

    obs_membro = ""
    if not eh_rf:
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
    page.wait_for_timeout(300)

    select_servico = modal_conteudo.locator('select:has-text("Selecione um Serviço"), select[name*="servico"]').first
    select_servico.focus()
    select_servico.select_option(label="Sem vínculo de serviço")
    select_servico.dispatch_event("change")
    select_servico.dispatch_event("input")
    page.wait_for_timeout(400)

    if eh_visita_rf:
        fila.put({"tipo": "log", "msg": "   -> [VISITA DOMICILIAR / RF]: Marcando caixas 'Visita Domiciliar' e 'Busca Ativa'...\n"})
        page.evaluate("""() => {
            const checkboxes = Array.from(document.querySelectorAll('#_iniciarAtendimento input[type="checkbox"]'));
            checkboxes.forEach(chk => {
                const rotulo = (chk.closest('tr, label, td, div') ? chk.closest('tr, label, td, div').innerText : '').toUpperCase();
                if (rotulo.includes('VISITA DOMICILIAR') || rotulo.includes('BUSCA ATIVA')) {
                    if (!chk.checked) chk.click();
                }
            });
        }""")
        page.wait_for_timeout(300)

    dialog_pai = modal_conteudo.locator('xpath=ancestor::div[contains(@class, "ui-dialog")]').first
    btn_iniciar_modal = dialog_pai.locator('.ui-dialog-buttonpane button:has-text("Iniciar"), button:has-text("Iniciar")').first
    btn_iniciar_modal.click()
    page.wait_for_timeout(2000)

    aplicar_saneamento_editar_familia(page, cod_fam_planilha, eh_visita_rf=eh_visita_rf, fila=fila)
    encerrar_atendimento_ativo(page, fila)
    retornar_para_busca(page)

    if eh_visita_rf:
        obs_membro = f" (Visita Domiciliar lançada){obs_membro}".strip()

    return obs_membro


def processar_automacao(caminho_planilha, pasta_destino_base, nome_aba, evento_login_pronto, fila, cancel_event):
    """Orquestrador principal chamado pela interface SuiteGesuasApp."""
    try:
        fila.put({"tipo": "log", "msg": f"[MOTOR GESUAS_BOT]: Iniciando rotina de lançamentos com suporte a Visita Domiciliar.\n"})
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
        col_obs_orig = next((c for c in df.columns if "OBS" in str(c).upper() or "VISITA" in str(c).upper()), "OBS")

        colunas_criticas = [col_gesuas, col_cod_fam, col_cpf, col_nome, col_servico, col_obs_orig]
        for c in colunas_criticas:
            if c in df.columns:
                df[c] = df[c].astype(object)
            else:
                df[c] = ""
                df[c] = df[c].astype(object)

        total_linhas = len(df)
        fila.put({"tipo": "log", "msg": f"[PLANILHA] {total_linhas} linhas mapeadas na aba {nome_aba}.\n"})

        fila.put({"tipo": "log", "msg": "[EDGE] Conectando ao Microsoft Edge na porta 9222...\n"})
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
                
                obs_planilha = str(linha.get(col_obs_orig, '')).strip() if col_obs_orig in df.columns else ""
                if obs_planilha.lower() in ['nan', 'none']:
                    obs_planilha = ""

                if not data_atend or not servico or servico in ['NAN', 'NONE']:
                    fila.put({"tipo": "log", "msg": f"\n[{num_linha}/{total_linhas}] Linha {num_linha}: Dados incompletos. A ignorar...\n"})
                    notificar_progresso()
                    continue

                data_hora_str = f"{data_atend} {hora_atend}".strip()
                status_gesuas_atual = str(linha.get(col_gesuas, '')).strip().upper()

                fila.put({"tipo": "log", "msg": f"\n[{num_linha}/{total_linhas}] Linha {num_linha}: {nome_municipe}\n"})
                fila.put({"tipo": "log", "msg": f" -> CPF: {cpf_raw} | Serviço: {servico} | Obs: {obs_planilha} | Data: {data_hora_str}\n"})

                eh_visita_planilha = eh_servico_visita_domiciliar(servico, obs_planilha)

                # REGRA 1: Pular se já estiver OK e NÃO for visita domiciliar
                if "OK" in status_gesuas_atual and not eh_visita_planilha:
                    fila.put({"tipo": "log", "msg": " -> [PULADO]: Atendimento comum já sinalizado como 'OK' na planilha.\n"})
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

                # REGRA 2: CONSULTA (COM OU SEM CÓDIGO FAMILIAR NA PLANILHA)
                if "CONSULTA" in servico:
                    cod_limpo = re.sub(r'\D', '', str(cod_fam_planilha)).strip() if cod_fam_planilha and str(cod_fam_planilha).lower() not in ['nan', 'none', 'nat'] else ""

                    if len(cod_limpo) != 11:
                        diag_consulta = obs_planilha if obs_planilha else "Consulta registrada (Sem código familiar na planilha)"
                        fila.put({"tipo": "log", "msg": f" -> [CONSULTA]: Sem código familiar de 11 dígitos ({obs_planilha or 'Sem código'}). Registro mantido.\n"})
                        df.at[idx, col_gesuas] = "OK (CONSULTA)"
                        alteracoes_feitas = True
                        resultados_robo.append({
                            "Linha": num_linha,
                            "Nome": nome_municipe,
                            "CPF": cpf_raw,
                            "Data": data_atend,
                            "Hora": hora_atend,
                            "Serviço": "CONSULTA",
                            "Cód. Familiar Planilha": cod_fam_planilha if cod_fam_planilha and str(cod_fam_planilha).lower() not in ['nan', 'none'] else "",
                            "Status Robô": "CONSULTA",
                            "Diagnóstico": diag_consulta
                        })
                        notificar_progresso()
                        continue

                    diag_consulta = "Consulta (Sem alteração de cadastro)"
                    achou = buscar_municipe(page, nome_municipe, cpf_raw, fila)
                    if achou:
                        status_acesso = verificar_pessoa_desligada_ou_acessar_familia(page, nome_municipe, fila)
                        if status_acesso != "DESLIGADA":
                            eh_rf, nome_rf_tela = verificar_titularidade_rf(page, cpf_raw, nome_municipe)
                            if eh_rf:
                                fila.put({"tipo": "log", "msg": f" -> [CONSULTA / RF]: Munícipe é o RF ({nome_rf_tela}). Saneando cadastro...\n"})
                                diag_consulta = sanear_consulta_ultimo_atendimento(page, cod_limpo, fila)
                            else:
                                fila.put({"tipo": "log", "msg": f" -> [CONSULTA / NÃO-RF]: Munícipe não é o RF ({nome_rf_tela}). Código não alterado.\n"})
                                retornar_para_busca(page)
                                diag_consulta = "Consulta mantida (Munícipe dependente)"
                        else:
                            retornar_para_busca(page)
                            diag_consulta = "Consulta - Munícipe desligado"
                    else:
                        diag_consulta = "Consulta - Munícipe não localizado no GESUAS"

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
                        "Diagnóstico": diag_consulta
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

                # 3. Identificação de Visita e Titularidade de RF
                eh_rf, nome_rf_tela = verificar_titularidade_rf(page, cpf_raw, nome_municipe)
                eh_visita_rf = eh_visita_planilha and eh_rf

                if eh_visita_planilha:
                    if eh_rf:
                        fila.put({"tipo": "log", "msg": f" -> [CRITÉRIO VISITA]: Munícipe é o RF ({nome_municipe}). Rota de Visita Domiciliar ativada.\n"})
                    else:
                        fila.put({"tipo": "log", "msg": f" -> [AVISO VISITA]: Munícipe NÃO é o RF (RF: {nome_rf_tela}). Visita restrita ao titular.\n"})

                # 4. Verificação de duplicidade / conferência de visita no GESUAS
                ja_tem, diag_visita = checar_duplicidade_e_adequar_visita(page, data_hora_str, data_atend, hora_atend, eh_visita_rf, cod_fam_planilha, fila)
                if ja_tem:
                    df.at[idx, col_gesuas] = "OK"
                    alteracoes_feitas = True
                    diag_final = diag_visita if diag_visita else (obs_planilha if obs_planilha else f"Atendimento existente em {data_hora_str} (Auditado)")
                    resultados_robo.append({
                        "Linha": num_linha,
                        "Nome": nome_municipe,
                        "CPF": cpf_raw,
                        "Data": data_atend,
                        "Hora": hora_atend,
                        "Serviço": servico,
                        "Cód. Familiar Planilha": cod_fam_planilha,
                        "Status Robô": "AUDITADO",
                        "Diagnóstico": diag_final
                    })
                    notificar_progresso()
                    continue

                # 5. Lançamento e encerramento de atendimento novo
                fila.put({"tipo": "log", "msg": f" -> [LANÇAMENTO]: A registrar atendimento de {servico} ({data_hora_str})...\n"})
                obs_membro = registrar_atendimento_completo(page, data_hora_str, nome_municipe, cod_fam_planilha, servico, obs_planilha, cpf_raw, fila)

                df.at[idx, col_gesuas] = "OK"
                alteracoes_feitas = True
                fila.put({"tipo": "log", "msg": f" -> [SUCESSO]: Atendimento registrado e encerrado no GESUAS com êxito!\n"})

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
        