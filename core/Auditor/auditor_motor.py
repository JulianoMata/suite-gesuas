# -*- coding: utf-8 -*-
"""
========================================================================================
SUITE GESUAS - CENTRAL DE OPERAÇÕES INTEGRADA (CRAS SUL - CAMPO BELO / MG)
MÓDULO: MOTOR DE RECONCILIAÇÃO E AUDITORIA (auditor_motor.py)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Cruza a composição cadastral extraída dos PDFs locais (CadÚnico) com os
            dados ativos raspados do GESUAS. Identifica membros faltantes para inclusão,
            membros a excluir, divergências de Código Familiar, alterações de RF e
            inconsistências de parentesco, gerando o status de intervenção necessário.
========================================================================================
"""


def conciliar_familia(dados_pdf: dict, dados_gesuas: dict) -> dict:
    """
    Compara a composição oficial do PDF com a composição registrada no GESUAS.
    Retorna o diagnóstico estruturado da família com regras estritas de intervenção.
    """
    cod_fam_pdf = dados_pdf.get("codigo_familiar", "")
    cod_fam_gesuas = dados_gesuas.get("codigo_familiar_gesuas", "")

    membros_pdf = dados_pdf.get("membros", [])
    membros_gesuas = dados_gesuas.get("membros_gesuas", [])

    # Dicionários indexados por CPF limpo (11 dígitos)
    mapa_pdf = {m["cpf_limpo"]: m for m in membros_pdf if m.get("cpf_limpo")}
    mapa_gesuas = {m["cpf_limpo"]: m for m in membros_gesuas if m.get("cpf_limpo")}

    cpfs_pdf = set(mapa_pdf.keys())
    cpfs_gesuas = set(mapa_gesuas.keys())

    # 1. Identificação de divergências de membros (inclusões e exclusões)
    cpfs_para_incluir = cpfs_pdf - cpfs_gesuas
    cpfs_para_excluir = cpfs_gesuas - cpfs_pdf

    nomes_incluir = [
        f"{mapa_pdf[c]['nome_membro']} ({mapa_pdf[c]['cpf_formatado']}) - Parentesco CadÚnico: {mapa_pdf[c].get('parentesco', 'Não informado')}"
        for c in cpfs_para_incluir
    ]
    nomes_excluir = [
        f"{mapa_gesuas[c]['nome']} ({mapa_gesuas[c].get('cpf_formatado', c)}) - Parentesco GESUAS: {mapa_gesuas[c].get('parentesco', 'Não informado')}"
        for c in cpfs_para_excluir
    ]

    # 2. Identificação de falha de leitura / Não Identificado no PDF
    tem_membro_nao_identificado = any("NÃO IDENTIFICADO" in m.get("nome_membro", "").upper() for m in membros_pdf)

    # 3. Verificação de Responsável Familiar / Pessoa de Referência
    # RF no CadÚnico: prioriza a marcação eh_rf obtida pelo texto de parentesco
    rf_pdf = next((m for m in membros_pdf if m.get("eh_rf")), membros_pdf[0] if membros_pdf else None)

    # RF no GESUAS: busca por termo de referência no parentesco cadastrado
    rf_gesuas = next(
        (m for m in membros_gesuas if "refer" in m.get("parentesco", "").lower()),
        membros_gesuas[0] if membros_gesuas else None
    )

    troca_rf = False
    detalhe_rf = ""
    if rf_pdf and rf_gesuas:
        cpf_rf_pdf = rf_pdf.get("cpf_limpo")
        cpf_rf_gesuas = rf_gesuas.get("cpf_limpo")
        if cpf_rf_pdf and cpf_rf_gesuas and cpf_rf_pdf != cpf_rf_gesuas:
            troca_rf = True
            parentesco_pdf_rf = rf_pdf.get("parentesco", "RF")
            parentesco_gesuas_rf = rf_gesuas.get("parentesco", "Pessoa de referência")
            detalhe_rf = (
                f"CadÚnico RF: {rf_pdf['nome_membro']} [{parentesco_pdf_rf}] | "
                f"GESUAS RF: {rf_gesuas['nome']} [{parentesco_gesuas_rf}]"
            )

    # 4. Verificação Estrita do Código Familiar (não pode estar vazio no GESUAS)
    divergencia_codigo = False
    motivo_codigo = ""
    if not cod_fam_gesuas:
        divergencia_codigo = True
        motivo_codigo = f"Código Familiar não preenchido no GESUAS (CadÚnico: {cod_fam_pdf})"
    elif cod_fam_pdf and (cod_fam_pdf != cod_fam_gesuas):
        divergencia_codigo = True
        motivo_codigo = f"Código Fam. divergente (PDF: {cod_fam_pdf} vs GESUAS: {cod_fam_gesuas})"

    # 5. Consolidação de Motivos de Intervenção
    motivos = []
    if divergencia_codigo:
        motivos.append(motivo_codigo)
    if nomes_incluir:
        motivos.append(f"Incluir no GESUAS: {', '.join(nomes_incluir)}")
    if nomes_excluir:
        motivos.append(f"Excluir do GESUAS: {', '.join(nomes_excluir)}")
    if troca_rf:
        motivos.append(f"Divergência de RF: {detalhe_rf}")
    if tem_membro_nao_identificado:
        motivos.append("Inconsistência na identificação de membro familiar no comprovante")

    precisa_intervencao = len(motivos) > 0

    return {
        "codigo_familiar_pdf": cod_fam_pdf,
        "codigo_familiar_gesuas": cod_fam_gesuas,
        "pasta_rf": dados_pdf.get("pasta_rf", ""),
        "total_membros_pdf": len(membros_pdf),
        "total_membros_gesuas": len(membros_gesuas),
        "precisa_intervencao": precisa_intervencao,
        "status": "INTERVENÇÃO NECESSÁRIA" if precisa_intervencao else "SINCRONIZADO (OK)",
        "detalhamento": " | ".join(motivos) if motivos else "Composição e dados consistentes"
    }
    