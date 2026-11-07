# -*- coding: utf-8 -*-
"""
========================================================================================
SISTEMA DE AUTOMAÇÃO DE ATENDIMENTOS E ATUALIZAÇÃO - GESUAS
MÓDULO: MOTOR DE AUTOMAÇÃO WEB PLAYWRIGHT (gesuas_bot.py)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Implementa o pipeline de navegação assistida na plataforma GESUAS com:
            - Detecção e normalização semântica de Visitas Domiciliares (SERVICO e OBS);
            - Validação estrita de Responsável Familiar (RF) em tela;
            - Abertura da linha real de atendimento no histórico para edição de Visita;
            - Em CONSULTA com RF: reabre último atendimento se código faltar ou divergir;
            - Encerramento estrito marcando exclusivamente a 3ª opção;
            - Fechamento resiliente via DOM sem travamento por ui-widget-overlay.
========================================================================================
"""

import os
import time
import re
import subprocess
import unicodedata
from importlib import import_module
import sys
from pathlib import Path

for _base in (Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[1]):
    if str(_base) not in sys.path:
        sys.path.insert(0, str(_base))

_notificacoes = import_module("SCRIPTS.notificacoes")
alerta_intervencao_manual = _notificacoes.alerta_intervencao_manual
alerta_confirmacao_visual = _notificacoes.alerta_confirmacao_visual
PORTA_DEBUG = import_module("SCRIPTS.config").PORTA_DEBUG


def normalizar_texto(texto: str) -> str:
    """Remove acentuações e caracteres especiais, retornando texto em caixa alta."""
    if not texto or not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    return re.sub(r'\s+', ' ', texto).strip().upper()


def eh_servico_visita_domiciliar(servico_raw: str, obs_raw: str = "") -> bool:
    """Classifica se a descrição da planilha corresponde à visita/entrevista em domicílio."""
    texto_combinado = f"{normalizar_texto(servico_raw)} {normalizar_texto(obs_raw)}"
    termos = ["VISITA", "DOMICILI", "DOMICILIO", "EM DOMICILIO", "ENTREVISTA DOMICILIAR"]
    return any(termo in texto_combinado for termo in termos)


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


def fechar_todas_modais_ativas(page):
    """Fecha com segurança qualquer modal do jQuery UI via JavaScript, ignorando sobreposições."""
    try:
        page.evaluate("""() => {
            const modais = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
            for (const m of modais) {
                const btnX = m.querySelector('.ui-dialog-titlebar-close');
                if (btnX) btnX.click();
            }
        }""")
        page.wait_for_timeout(400)
    except Exception:
        pass


def retornar_para_busca(page):
    """Garante retorno ao painel de busca clicando no botão '<' ou na sanfona."""
    fechar_todas_modais_ativas(page)
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


def buscar_municipe(page, nome, cpf, tipo_acao):
    """Executa a busca inteligente por CPF (se 11 dígitos) e fallback por Nome."""
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

    if "pessoa desligada" in texto_resultado or "desligada" in texto_resultado:
        print(f"   [AVISO] {nome} consta como 'PESSOA DESLIGADA' ({tipo_acao}). Pulando...")
        modal_add_familia = page.locator('.ui-dialog:visible:has-text("Adicionar à uma Família existente")')
        if modal_add_familia.count() > 0 and modal_add_familia.first.is_visible():
            btn_fechar_dialog = modal_add_familia.locator('.ui-dialog-titlebar-close, button[title="close"], .ui-icon-closethick').first
            if btn_fechar_dialog.is_visible():
                btn_fechar_dialog.click()
                page.wait_for_timeout(600)
        return "DESLIGADA"

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


def verificar_titularidade_rf(page, cpf_municipe, nome_municipe) -> tuple[bool, str]:
    """Valida se o munícipe atual é a Pessoa de Referência (RF) na composição familiar exibida."""
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
    """Extrai os dígitos do código familiar atualmente exibido no cabeçalho da família."""
    try:
        texto = page.evaluate("""() => {
            const el = Array.from(document.querySelectorAll('div, p, span, td'))
                            .find(e => e.innerText && e.innerText.includes('Cód. familiar:'));
            return el ? el.innerText : '';
        }""")
        return re.sub(r'\D', '', texto)
    except Exception:
        return ""


def aplicar_saneamento_editar_familia(page, cod_fam, eh_visita_rf: bool):
    """Acessa 'Editar família' na tela principal, sanitiza Código Familiar, limpa Telefones e define Forma de Acesso."""
    fechar_todas_modais_ativas(page)
    btn_editar_fam = page.locator('button:visible:has-text("Editar família"), a:visible:has-text("Editar família")').first
    try:
        btn_editar_fam.wait_for(state="visible", timeout=6000)
        btn_editar_fam.click()
        page.wait_for_timeout(1000)
    except Exception:
        return

    modal_fam = page.locator('.ui-dialog:visible:has-text("Editar família"), div[role="dialog"]:visible:has-text("Editar família")').last
    if not modal_fam.is_visible():
        return

    # 1. Código Familiar
    if cod_fam and str(cod_fam).strip() and str(cod_fam).lower() not in ['nan', 'none']:
        cod_limpo = re.sub(r'\D', '', str(cod_fam)).strip()
        campo_cod = modal_fam.locator('text="Código familiar"').locator('xpath=following-sibling::input | ../following-sibling::*//input | following::input[1]').first
        if not campo_cod.is_visible():
            campo_cod = modal_fam.locator('input[name*="codigo_familiar"], input[id*="codigo_familiar"]').first

        if campo_cod.is_visible():
            campo_cod.click()
            campo_cod.press("Control+A")
            campo_cod.press("Backspace")
            campo_cod.type(cod_limpo, delay=25)
            page.wait_for_timeout(150)

    # 2. Limpeza de Telefones
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

    # 4. Gravação da modal 'OK'
    btn_ok = modal_fam.locator('button:visible:has-text("OK"), .ui-dialog-buttonpane button:has-text("OK")').first
    if btn_ok.is_visible():
        btn_ok.click()
        page.wait_for_timeout(1500)


def encerrar_atendimento_ativo(page):
    """
    Encerra atendimento aberto na tela da família:
    Desmarca acompanhamento particularizado, marca exclusivamente
    'Cadastramento/Atualização Cadastral na GESUAS' e clica em OK.
    """
    btn_encerrar = page.locator('a:has-text("Encerrar atendimento"), button:has-text("Encerrar atendimento")').first
    try:
        btn_encerrar.wait_for(state="visible", timeout=6000)
    except Exception:
        return

    btn_encerrar.click()
    page.wait_for_timeout(1200)

    fechou_ok = page.evaluate("""() => {
        const dialogs = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
        const modalEncerrar = dialogs.find(d => d.innerText.includes('Encerrar Atendimento') || d.innerText.includes('Tipos'));
        if (!modalEncerrar) return false;

        const checkboxes = Array.from(modalEncerrar.querySelectorAll('input[type="checkbox"]'));
        checkboxes.forEach(chk => {
            const rotuloContainer = chk.closest('label') || chk.closest('tr') || chk.parentElement;
            const texto = rotuloContainer ? rotuloContainer.innerText.toUpperCase() : '';

            if (texto.includes('CADASTRAMENTO') || texto.includes('ATUALIZACAO') || texto.includes('ATUALIZAÇÃO')) {
                if (!chk.checked) chk.click();
            } else {
                if (chk.checked) chk.click();
            }
        });

        const btnOk = Array.from(modalEncerrar.querySelectorAll('button, a')).find(b => b.innerText.trim().toUpperCase() === 'OK');
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


def sanear_consulta_ultimo_atendimento(page, cod_fam_planilha) -> str:
    """
    Exclusivo para CONSULTA realizada pelo RF:
    Se código faltar ou divergir: abre 'Editar um Atendimento', reabre o mais recente via 'Iniciar',
    saneia em 'Editar família', encerra com 'Cadastramento/Atualização' e volta para a busca.
    """
    cod_planilha_limpo = re.sub(r'\D', '', str(cod_fam_planilha)).strip()
    cod_tela_limpo = obter_codigo_familiar_tela(page)

    if cod_tela_limpo and cod_tela_limpo == cod_planilha_limpo:
        print(f"   -> [CONSULTA]: Código Familiar ({cod_tela_limpo}) já coincide com a planilha. Sem alterações.")
        retornar_para_busca(page)
        return "Consulta - Código já atualizado"

    print(f"   -> [DIVERGÊNCIA/AUSÊNCIA]: Código no GESUAS ('{cod_tela_limpo}') difere da planilha ('{cod_planilha_limpo}').")
    print("   -> Acessando histórico em 'Editar um Atendimento' para vincular alteração...")

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
        print("   -> [CONSULTA]: Família sem atendimentos anteriores registrados. Desconsiderando saneamento...")
        fechar_todas_modais_ativas(page)
        retornar_para_busca(page)
        return "Consulta mantida (Sem atendimentos anteriores)"

    print("   -> Reabrindo último atendimento via botão 'Iniciar'...")
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

    aplicar_saneamento_editar_familia(page, cod_planilha_limpo, eh_visita_rf=False)
    encerrar_atendimento_ativo(page)
    retornar_para_busca(page)

    return "Consulta - Código Familiar saneado no último atendimento"


def checar_duplicidade_e_adequar_visita(page, nome, tipo_acao, data_hora_str, data_atend, hora_atend, eh_visita_rf: bool, cod_fam: str) -> tuple[bool, str]:
    """Verifica duplicidade e, se for Visita Domiciliar pré-existente com RF, entra na linha para marcar Visita e Busca Ativa."""
    btn_editar = page.locator('button:visible:has-text("Editar um Atendimento"), a:visible:has-text("Editar um Atendimento")').first
    try:
        btn_editar.wait_for(state="visible", timeout=6000)
    except Exception:
        return False, ""

    btn_editar.click()
    page.wait_for_timeout(1800)

    dados_historico = page.evaluate("""(alvoDataHora) => {
        const dialogs = Array.from(document.querySelectorAll('.ui-dialog, div[role="dialog"]'))
                             .filter(el => el.offsetWidth > 0 && el.offsetHeight > 0);
        let textoCompleto = '';
        for (const d of dialogs) {
            textoCompleto += ' ' + d.innerText;
        }
        return {
            texto: textoCompleto,
            existe: textoCompleto.includes(alvoDataHora)
        };
    }""", data_hora_str)

    texto_limpo = " ".join(dados_historico["texto"].split())
    ja_cadastrado = dados_historico["existe"] or (data_atend in texto_limpo and hora_atend in texto_limpo)

    if not ja_cadastrado and "Editar" not in texto_limpo and "Data do atendimento" not in texto_limpo:
        ja_cadastrado = alerta_confirmacao_visual(nome, tipo_acao, data_hora_str)

    diag_visita = ""

    if ja_cadastrado:
        print(f"   -> [HISTÓRICO LOCALIZADO]: Atendimento de {data_hora_str} encontrado no histórico.")
        
        # Clica no botão/ícone de edição da linha com a data alvo
        page.evaluate("""(dataAlvo) => {
            const dialogs = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"])'));
            for (const d of dialogs) {
                const linhas = Array.from(d.querySelectorAll('tr, .ui-widget-content'));
                for (const tr of linhas) {
                    if (tr.innerText.includes(dataAlvo)) {
                        const btnEd = tr.querySelector('a, button, .ui-icon-pencil');
                        if (btnEd) {
                            btnEd.click();
                            return true;
                        }
                    }
                }
            }
            const botoes = Array.from(document.querySelectorAll('.ui-dialog:not([style*="display: none"]) a, .ui-dialog:not([style*="display: none"]) button'))
                                .filter(b => (b.innerText && b.innerText.toUpperCase().includes('EDITAR')) || (b.title && b.title.toLowerCase().includes('editar')));
            if (botoes.length > 0) {
                botoes[0].click();
                return true;
            }
            return false;
        }""", data_atend)
        page.wait_for_timeout(1500)

        if eh_visita_rf:
            print("   -> Marcando checkboxes 'Visita Domiciliar' e 'Busca Ativa'...")
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

            print("   -> Gravando edição do atendimento no botão 'Iniciar'...")
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

            aplicar_saneamento_editar_familia(page, cod_fam, eh_visita_rf=True)
            encerrar_atendimento_ativo(page)
            diag_visita = "Visita Domiciliar editada e confirmada no GESUAS"

        else:
            print("   -> Atendimento comum já existente. Fechando histórico...")
            fechar_todas_modais_ativas(page)
            diag_visita = "Atendimento comum existente (Auditado)"

        retornar_para_busca(page)
        return True, diag_visita

    fechar_todas_modais_ativas(page)
    return False, ""


def registrar_atendimento_e_encerrar(page, data_hora_str, nome, tipo_acao, obs_planilha="", cpf_municipe="", cod_fam=""):
    """Preenche atendimento novo com separação entre Demanda Espontânea e Visita Domiciliar/RF."""
    eh_visita = eh_servico_visita_domiciliar(tipo_acao, obs_planilha)
    eh_rf, nome_rf_tela = verificar_titularidade_rf(page, cpf_municipe, nome)
    eh_visita_rf = eh_visita and eh_rf

    btn_iniciar_tela = page.locator('button:visible:has-text("Iniciar atendimento"), a:visible:has-text("Iniciar atendimento")').filter(has_not=page.locator('#btnNovaFamiliaIniciarAtendimento')).first
    btn_iniciar_tela.wait_for(state="visible", timeout=7000)
    btn_iniciar_tela.click()
    page.wait_for_timeout(1000)

    modal_conteudo = page.locator('#_iniciarAtendimento')
    modal_conteudo.wait_for(state="visible", timeout=10000)
    page.wait_for_timeout(500)

    obs_membro = ""
    if not eh_rf:
        print(f"   [ALERTA MEMBRO] Munícipe ({nome}) NÃO é o RF (RF: {nome_rf_tela}). Ajustando checkboxes...")
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
        print("   -> Marcando checkboxes: 'Visita Domiciliar' e 'Busca Ativa'...")
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

    aplicar_saneamento_editar_familia(page, cod_fam, eh_visita_rf=eh_visita_rf)
    encerrar_atendimento_ativo(page)
    retornar_para_busca(page)

    if eh_visita_rf:
        obs_membro = f" (Visita Domiciliar realizada){obs_membro}".strip()

    return obs_membro
