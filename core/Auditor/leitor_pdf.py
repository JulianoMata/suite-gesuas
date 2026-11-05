# -*- coding: utf-8 -*-
"""
========================================================================================
SUITE GESUAS - CENTRAL DE OPERAÇÕES INTEGRADA (CRAS SUL - CAMPO BELO / MG)
MÓDULO: EXTRATOR DE DADOS DE COMPROVANTES EM PDF (leitor_pdf.py)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Lê os comprovantes do CadÚnico por blocos atômicos, extraindo com precisão
            Código Familiar, integrantes, CPF e elegendo o Responsável Familiar (RF)
            exclusivamente pelo parentesco declarado oficial.
========================================================================================
"""

import os
import re
import pypdf
import pandas as pd


def localizar_caminho_dados() -> str:
    """
    Detecta automaticamente a unidade e o diretório onde está a pasta DADOS.
    Prioriza a nova estrutura: CADASTROUNICO\\DADOS.
    Mantém compatibilidade com caminhos antigos (VISITAS_).
    """
    candidatos_relativos = [
        os.path.join("CADASTROUNICO", "DADOS"),
        "VISITAS_",
    ]

    # 1. Testa primeiro na unidade padrão E:
    for rel in candidatos_relativos:
        caminho_e = os.path.join("E:\\", rel)
        if os.path.exists(caminho_e):
            return caminho_e

    # 2. Testa em qualquer outra letra de unidade conectada (D: a Z:)
    for letra in "DEFGHIJKLMNOPQRSTUVWXYZ":
        for rel in candidatos_relativos:
            caminho_teste = f"{letra}:\\{rel}"
            if os.path.exists(caminho_teste):
                return caminho_teste

    # Fallback padrão
    return r"E:\CADASTROUNICO\DADOS"


CAMINHO_BASE_DADOS = localizar_caminho_dados()


def listar_anos_disponiveis() -> list:
    """Retorna as pastas de anos encontradas dentro de DADOS (ex: CADASTRO2025, CADASTRO2026)."""
    if not os.path.exists(CAMINHO_BASE_DADOS):
        return []
    pastas = [
        p for p in os.listdir(CAMINHO_BASE_DADOS)
        if os.path.isdir(os.path.join(CAMINHO_BASE_DADOS, p)) and "CADASTRO" in p.upper()
    ]
    pastas.sort()
    return pastas


def extrair_dados_comprovante_pdf(caminho_pdf):
    """
    Lê o comprovante PDF do CadÚnico extraindo código familiar, integrantes,
    CPF, parentesco e identificação exata do Responsável Familiar (RF).
    """
    try:
        reader = pypdf.PdfReader(caminho_pdf)
        texto_completo = ""
        for page in reader.pages:
            t_pagina = page.extract_text() or ""
            texto_completo += t_pagina + "\n"
    except Exception as e:
        print(f"   [ERRO AO LER PDF] {caminho_pdf}: {e}")
        return "", []

    # 1. Código Familiar (11 dígitos normalizados com zfill)
    cod_fam_match = re.search(r'C[oó]digo\s*familiar[:\s]*\n?\s*(\d+)', texto_completo, re.IGNORECASE)
    if not cod_fam_match:
        cod_fam_match = re.search(r'\b(\d{7,11})\b', texto_completo)

    cod_bruto = cod_fam_match.group(1) if cod_fam_match else ""
    cod_familiar = re.sub(r'\D', '', cod_bruto).zfill(11) if cod_bruto else ""

    # 2. Recorte da Seção "Integrantes da família"
    if "Integrantes da família" in texto_completo:
        secao = texto_completo.split("Integrantes da família")[-1].split("Autenticidade")[0]
    else:
        secao = texto_completo

    linhas = [l.strip() for l in secao.splitlines() if l.strip()]

    # Filtra cabeçalhos da tabela do CadÚnico
    linhas = [
        l for l in linhas 
        if not any(c in l.lower() for c in ["parentesco com o rf", "estado cadastral", "data de nascimento", "nis, pis ou pasep"])
    ]

    padrao_cpf = re.compile(r'(\d{3}\.\d{3}\.\d{3}-\d{2})')

    # Recomposição de linhas caso o pypdf divida os campos de um membro em linhas separadas
    linhas_recompostas = []
    buffer = ""
    for l in linhas:
        if padrao_cpf.search(l):
            if buffer:
                linhas_recompostas.append(buffer + " " + l)
                buffer = ""
            else:
                linhas_recompostas.append(l)
        else:
            if buffer:
                buffer += " " + l
            else:
                buffer = l
    if buffer:
        linhas_recompostas.append(buffer)

    membros = []
    padrao_linha_estrita = re.compile(
        r'^(?P<nome>[A-ZÀ-Ú\s]+?)\s+'
        r'(?P<cpf>\d{3}\.\d{3}\.\d{3}-\d{2})\s+'
        r'(?P<nasc>\d{2}/\d{2}/\d{4})\s+'
        r'(?P<nis>\d+)\s+'
        r'(?P<estado>[A-Za-zÀ-ú]+)\s+'
        r'(?P<parentesco>.+)$'
    )

    for lr in linhas_recompostas:
        m = padrao_linha_estrita.search(lr)
        if m:
            nome = re.sub(r'\s+', ' ', m.group('nome')).strip()
            cpf_fmt = m.group('cpf')
            cpf_limpo = re.sub(r'\D', '', cpf_fmt)
            parentesco = re.sub(r'\s+', ' ', m.group('parentesco')).strip()
        else:
            cpf_m = padrao_cpf.search(lr)
            if not cpf_m:
                continue
            cpf_fmt = cpf_m.group(1)
            cpf_limpo = re.sub(r'\D', '', cpf_fmt)
            partes = lr.split(cpf_fmt)
            nome = re.sub(r'[^A-ZÀ-Úa-zà-ú\s]', ' ', partes[0]).strip()
            nome = re.sub(r'\s+', ' ', nome)

            pos_cpf = partes[1] if len(partes) > 1 else ""
            parentesco_match = re.search(r'(?:Cadastrado|Atualizado|Exclu[íi]do|[A-Za-z]+)\s+(.+)$', pos_cpf)
            if parentesco_match:
                parentesco = parentesco_match.group(1).strip()
            else:
                parentesco = "Não informado"

        if not nome:
            nome = "NÃO IDENTIFICADO"

        # Identificação estrita do RF baseada exclusivamente no texto oficial de parentesco
        eh_rf = bool(re.search(r'respons[áa]vel|unidade familiar - rf|\brf\b', parentesco, re.IGNORECASE))

        membros.append({
            "codigo_familiar": cod_familiar,
            "nome_membro": nome,
            "cpf_limpo": cpf_limpo,
            "cpf_formatado": cpf_fmt,
            "parentesco": parentesco,
            "eh_rf": eh_rf
        })

    # Regra de contingência: se nenhum membro foi marcado com texto de RF (ex: caso de folha única abreviada)
    if membros and not any(m["eh_rf"] for m in membros):
        membros[0]["eh_rf"] = True

    return cod_familiar, membros


def analisar_pasta_mes(pasta_ano="CADASTRO2026", nome_pasta_mes="10-OUTUBRO"):
    """Varre as pastas de famílias de um ano/mês específico e consolida os dados."""
    caminho_mes = os.path.join(CAMINHO_BASE_DADOS, pasta_ano, nome_pasta_mes)

    if not os.path.exists(caminho_mes):
        print(f"[ALERTA] Diretório não encontrado: {caminho_mes}")
        return None

    print(f"\nIniciando leitura dos comprovantes em: {caminho_mes}\n" + "-" * 70)

    registros = []
    pastas = [p for p in os.listdir(caminho_mes) if os.path.isdir(os.path.join(caminho_mes, p))]
    print(f"Total de pastas familiares encontradas no mês: {len(pastas)}")

    for pasta_rf in pastas:
        caminho_rf = os.path.join(caminho_mes, pasta_rf)
        for arquivo in os.listdir(caminho_rf):
            if arquivo.lower().startswith("comprovante de cadastro") and arquivo.lower().endswith(".pdf"):
                caminho_pdf = os.path.join(caminho_rf, arquivo)
                cod_fam, membros = extrair_dados_comprovante_pdf(caminho_pdf)
                for m in membros:
                    registros.append({
                        "ano": pasta_ano,
                        "pasta_rf": pasta_rf,
                        "codigo_familiar": cod_fam,
                        "nome_membro": m["nome_membro"],
                        "cpf_formatado": m["cpf_formatado"],
                        "cpf_limpo": m["cpf_limpo"],
                        "parentesco": m["parentesco"],
                        "eh_rf": "SIM" if m["eh_rf"] else "NÃO",
                        "arquivo_pdf": arquivo
                    })
                break

    df = pd.DataFrame(registros)
    return df


if __name__ == "__main__":
    anos_disp = listar_anos_disponiveis()
    print("Anos disponíveis encontrados:", anos_disp)
    ano_teste = anos_disp[-1] if anos_disp else "CADASTRO2026"
    df_resultado = analisar_pasta_mes(ano_teste, "10-OUTUBRO")
    if df_resultado is not None and not df_resultado.empty:
        print("\n" + "=" * 70)
        print(f"EXTRAÇÃO CONCLUÍDA! Total de membros lidos: {len(df_resultado)}")
        print("=" * 70)
        print(df_resultado[["pasta_rf", "codigo_familiar", "eh_rf", "nome_membro", "parentesco", "cpf_formatado"]].head(15).to_string())
        