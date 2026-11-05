# -*- coding: utf-8 -*-
"""
========================================================================================
SUITE GESUAS - CENTRAL DE OPERAÇÕES INTEGRADA (CRAS SUL - CAMPO BELO / MG)
MÓDULO: RASPAGEM DA COMPOSIÇÃO FAMILIAR NO GESUAS (extrator_gesuas.py)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Conecta à sessão ativa do Microsoft Edge via CDP, pesquisa a família pelo
            CPF do Responsável Familiar no GESUAS, abre o prontuário familiar e 
            raspa a tabela de 'Composição Familiar' (Nome, CPF limpo, Sexo, Idade,
            Parentesco e Código Familiar do GESUAS com normalização de 11 dígitos).
========================================================================================
"""

import re
import time
from playwright.sync_api import Page

def fechar_modal_erro_busca(page: Page):
    """Fecha diálogos de erro que possam travar a busca."""
    modal_erro = page.locator('.ui-dialog:visible:has-text("Erro ao efetuar busca")')
    if modal_erro.count() > 0 and modal_erro.first.is_visible():
        btn_ok = modal_erro.locator('button:has-text("OK"), .ui-dialog-buttonpane button').first
        if btn_ok.is_visible():
            btn_ok.click()
        else:
            modal_erro.locator('.ui-dialog-titlebar-close').first.click()
        page.wait_for_timeout(500)

def retornar_para_busca(page: Page):
    """Retorna à tela de busca se estiver dentro de um prontuário."""
    btn_voltar = page.locator('button:has-text("Agendar Atendimento"), a:has-text("Agendar Atendimento")').locator('xpath=preceding-sibling::*[1]').first
    if not btn_voltar.is_visible():
        btn_voltar = page.locator('a:visible:has-text("<"), button:visible:has-text("<")').first
        
    if btn_voltar.is_visible():
        btn_voltar.click()
        page.wait_for_timeout(1000)

    campo_cpf = page.locator('#pessoa_search_cpf')
    if not campo_cpf.is_visible():
        aba_buscar = page.locator('text="Buscar pessoa"').first
        if aba_buscar.is_visible():
            aba_buscar.click()
            page.wait_for_timeout(500)

def acessar_familia_por_cpf(page: Page, cpf_rf: str) -> tuple[bool, str]:
    """
    Busca o munícipe pelo CPF do RF.
    Retorna uma tupla (sucesso: bool, motivo: str):
      - (True, "OK"): Cadastro aberto com sucesso.
      - (False, "DESLIGADA"): Pessoa encontrada, mas desligada no GESUAS.
      - (False, "NAO_ENCONTRADO"): Ninguém localizado pelo CPF.
    """
    retornar_para_busca(page)
    campo_cpf = page.locator('#pessoa_search_cpf')
    campo_cpf.wait_for(state="visible", timeout=6000)
    campo_cpf.click()
    campo_cpf.fill(cpf_rf)
    
    page.locator('#btn_procurar, button:has-text("Procurar..."), a:has-text("Procurar...")').first.click()
    page.wait_for_timeout(1200)
    fechar_modal_erro_busca(page)

    if page.locator('text="Não foram encontradas pessoas"').is_visible() or not page.locator('text="Pessoas encontradas"').is_visible():
        return False, "NAO_ENCONTRADO"

    # Verificação de Pessoa Desligada
    area_pessoas = page.locator('#pessoasListDiv, div:has-text("Pessoas encontradas")').first
    texto_resultado = area_pessoas.inner_text().lower() if area_pessoas.is_visible() else ""

    if "pessoa desligada" in texto_resultado:
        # Extrai o motivo se estiver visível (ex: Mudança de família)
        match_motivo = re.search(r'pessoa desligada\.?\s*motivo:\s*([^\n\r]+)', texto_resultado, re.IGNORECASE)
        motivo_txt = match_motivo.group(0).strip() if match_motivo else "Pessoa desligada no prontuário"
        return False, f"DESLIGADA: {motivo_txt.title()}"

    # Clica no boneco para ver o cadastro da família
    btn_boneco = page.locator('a[title*="Ver cadastro da família"], button[title*="Ver cadastro da família"]').first
    if not btn_boneco.is_visible():
        btn_boneco = page.locator('#pessoasListDiv .ui-button, #pessoasListDiv button, #pessoasListDiv a').first
        
    if btn_boneco.is_visible():
        btn_boneco.click(force=True)
        page.wait_for_timeout(1800)
        return True, "OK"

    return False, "SEM_BOTAO_FAMILIA"

def extrair_codigo_familiar_gesuas(page: Page) -> str:
    """
    Extrai o Código Familiar com 11 dígitos garantidos:
    1. Busca global no DOM (por Cód. Familiar, Código Familiar, etc.);
    2. Se não encontrar, clica em 'Detalhes da família', extrai e fecha o modal.
    """
    cod_fam = ""

    # Tentativa 1: Varredura em todo o texto visível da tela
    try:
        texto_geral = page.inner_text("body")
        padrao = r'(?:c[oó]d(?:igo)?\.?\s*familiar[:\s]*)([\d\.\-]+)'
        match = re.search(padrao, texto_geral, re.IGNORECASE)
        if match:
            cod_limpo = re.sub(r'\D', '', match.group(1))
            if len(cod_limpo) >= 7:
                return cod_limpo.zfill(11)
    except Exception:
        pass

    # Tentativa 2: Modal 'Detalhes da família'
    btn_detalhes = page.locator('button:has-text("Detalhes da família"), a:has-text("Detalhes da família")').first
    if btn_detalhes.is_visible():
        try:
            btn_detalhes.click()
            page.wait_for_timeout(800)
            modal = page.locator('.ui-dialog:visible').first
            if modal.is_visible():
                txt_modal = modal.inner_text()
                match_modal = re.search(r'(?:c[oó]d(?:igo)?\.?\s*familiar[:\s]*)([\d\.\-]+)', txt_modal, re.IGNORECASE)
                if match_modal:
                    cod_limpo = re.sub(r'\D', '', match_modal.group(1))
                    if len(cod_limpo) >= 7:
                        cod_fam = cod_limpo.zfill(11)

                btn_fechar = modal.locator('.ui-dialog-titlebar-close, button:has-text("Fechar")').first
                if btn_fechar.is_visible():
                    btn_fechar.click()
                    page.wait_for_timeout(400)
        except Exception:
            pass

    return cod_fam

def raspar_composicao_familiar_gesuas(page: Page) -> dict:
    """
    Extrai a composição familiar diretamente da tela do GESUAS:
    - Código familiar com 11 dígitos (zfill);
    - Descarta ícones e mensagens de validação (triângulo de alerta);
    - Captura Nome real, CPF (11 dígitos) e Parentesco de cada membro.
    """
    page.locator('text="Composição Familiar"').wait_for(state="visible", timeout=8000)
    page.wait_for_timeout(400)

    # 1. Código Familiar do GESUAS
    cod_fam_gesuas = extrair_codigo_familiar_gesuas(page)

    # 2. Raspagem via DOM no navegador
    membros_gesuas = page.evaluate("""() => {
        const membros = [];
        const container = Array.from(document.querySelectorAll('div, fieldset'))
                               .find(el => el.innerText && el.innerText.includes('Composição Familiar'));
        const tabela = container ? container.querySelector('table') : document.querySelector('table');
        if (!tabela) return membros;

        const linhas = Array.from(tabela.querySelectorAll('tbody tr'));
        for (const tr of linhas) {
            const colunas = Array.from(tr.querySelectorAll('td'));
            if (colunas.length >= 5) {
                // Clona a célula do nome para remover ícones de alerta sem alterar a tela
                const tdNome = colunas[0].cloneNode(true);
                
                // Remove ícones de alerta, tooltips ou botões internos
                tdNome.querySelectorAll('span, i, img, [title*="Campos"], .ui-icon').forEach(el => el.remove());
                
                // O que sobra é estritamente o Nome da pessoa
                let nomeReal = tdNome.innerText.replace(/▲|!/g, '').replace(/\\.\\.\\.$/, '').trim();

                const cpfTexto = colunas[1].innerText.replace(/\\D/g, '');
                const sexo = colunas[2].innerText.trim();
                const idade = colunas[3].innerText.trim();
                const parentesco = colunas[4].innerText.trim();

                membros.push({
                    nome: nomeReal,
                    cpf_limpo: cpfTexto.padStart(11, '0'),
                    sexo: sexo,
                    idade: idade,
                    parentesco: parentesco
                });
            }
        }
        return membros;
    }""")

    # 3. Formatação dos CPFs
    for m in membros_gesuas:
        cpf_num = m["cpf_limpo"]
        if len(cpf_num) == 11 and cpf_num != "00000000000":
            m["cpf_formatado"] = f"{cpf_num[:3]}.{cpf_num[3:6]}.{cpf_num[6:9]}-{cpf_num[9:]}"
        else:
            m["cpf_formatado"] = cpf_num

    return {
        "codigo_familiar_gesuas": cod_fam_gesuas,
        "membros_gesuas": membros_gesuas
    }
    