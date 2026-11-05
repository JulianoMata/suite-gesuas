# -*- coding: utf-8 -*-
"""
========================================================================================
SUITE GESUAS - CENTRAL DE OPERAÇÕES INTEGRADA (CRAS SUL - CAMPO BELO / MG)
MÓDULO: CONTROLADOR DO MOTOR DE AUDITORIA (auditor_engine.py)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Orquestrador da esteira de auditoria cadastral. Lê os PDFs das famílias via
            leitor_pdf, executa a busca ativa no GESUAS por CPF do RF via Playwright CDP,
            concilia os dados e grava os relatórios com versionamento cronológico.
========================================================================================
"""

import os
import sys
import re
import json
import time
import subprocess
from datetime import datetime
from playwright.sync_api import sync_playwright

DIRETORIO_ATUAL = os.path.dirname(os.path.abspath(__file__))
if DIRETORIO_ATUAL not in sys.path:
    sys.path.insert(0, DIRETORIO_ATUAL)

import leitor_pdf
import extrator_gesuas
import auditor_motor
import gerador_relatorio_pdf


def abrir_edge_depuracao():
    """Inicia o Edge com depuração CDP na porta 9222 se ainda não estiver aberto."""
    caminho_edge = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if not os.path.exists(caminho_edge):
        caminho_edge = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    
    comando = f'"{caminho_edge}" --remote-debugging-port=9222 --user-data-dir="C:\\temp_edge_gesuas"'
    subprocess.Popen(comando, shell=True)


def processar_auditoria(pasta_mes, pasta_destino_base, evento_confirmacao_login, fila, cancel_event, forcar_reinicio=False):
    """
    Executa a auditoria completa preservando a cronologia de execuções.
    """
    try:
        fila.put({"tipo": "log", "msg": f"[INÍCIO] Pasta de análise: {pasta_mes}\n"})

        # 1. Criação das subpastas organizadas de saída
        pasta_checkpoints = os.path.join(pasta_destino_base, "CHECKPOINTS")
        pasta_planilhas = os.path.join(pasta_destino_base, "PLANILHAS_EXCEL")
        pasta_relatorios = os.path.join(pasta_destino_base, "RELATORIOS_PDF")

        for p in [pasta_checkpoints, pasta_planilhas, pasta_relatorios]:
            os.makedirs(p, exist_ok=True)

        fila.put({"tipo": "log", "msg": f"[PASTAS] Estrutura organizada pronta em:\n -> {pasta_destino_base}\n"})

        # 2. Mapeamento estrito: dentro de 'pasta_mes' cada subpasta é um Responsável Familiar
        familias_alvo = {}
        subpastas_rf = [
            d for d in os.listdir(pasta_mes)
            if os.path.isdir(os.path.join(pasta_mes, d)) and not d.startswith(".")
        ]

        for nome_rf in sorted(subpastas_rf):
            caminho_rf = os.path.join(pasta_mes, nome_rf)
            arquivos = os.listdir(caminho_rf)

            # Prioriza 'Comprovante de cadastro' e depois 'Folha Resumo'
            pdf_comprovante = None
            pdf_folha = None

            for f in arquivos:
                f_low = f.lower()
                if f_low.endswith(".pdf"):
                    if "comprovante de cadastro" in f_low:
                        pdf_comprovante = os.path.join(caminho_rf, f)
                    elif "folha resumo" in f_low:
                        pdf_folha = os.path.join(caminho_rf, f)

            pdf_escolhido = pdf_comprovante or pdf_folha
            if pdf_escolhido:
                familias_alvo[nome_rf] = pdf_escolhido

        if not familias_alvo:
            fila.put({"tipo": "log", "msg": "[AVISO] Nenhuma família com comprovante PDF compatível encontrada.\n"})
            fila.put({"tipo": "fim_auditoria", "sucesso": False})
            return

        total_familias = len(familias_alvo)
        fila.put({"tipo": "log", "msg": f"[INFO] {total_familias} famílias identificadas para auditoria cadastral.\n"})

        # 3. Gerenciamento do Checkpoint Cronológico (Ano + Mês)
        partes_caminho = [p for p in os.path.normpath(pasta_mes).split(os.sep) if p]
        nome_ano_mes = f"{partes_caminho[-2]}_{partes_caminho[-1]}" if len(partes_caminho) >= 2 else os.path.basename(pasta_mes)
        caminho_checkpoint = os.path.join(pasta_checkpoints, f"checkpoint_{nome_ano_mes}.json")

        processados = set()
        historico_auditoria = []

        if forcar_reinicio:
            fila.put({"tipo": "log", "msg": f"[CHECKPOINT] Modo reinício ativado: ignorando histórico anterior de {nome_ano_mes}.\n"})
        elif os.path.exists(caminho_checkpoint):
            try:
                with open(caminho_checkpoint, "r", encoding="utf-8") as cp:
                    dados_checkpoint = json.load(cp)
                    if isinstance(dados_checkpoint, dict):
                        processados = set(dados_checkpoint.get("processados", []))
                        historico_auditoria = dados_checkpoint.get("resultados", [])
                    elif isinstance(dados_checkpoint, list):
                        processados = set(dados_checkpoint)
                fila.put({"tipo": "log", "msg": f"[CHECKPOINT] Cronologia detectada: {len(processados)} famílias já auditadas em {nome_ano_mes}.\n"})
            except Exception:
                processados = set()
                historico_auditoria = []

        # 4. Inicialização do Edge e Confirmação de Login
        fila.put({"tipo": "log", "msg": "[EDGE] Abrindo Microsoft Edge na porta 9222...\n"})
        abrir_edge_depuracao()

        fila.put({
            "tipo": "aguardar_login",
            "msg": "Faça login no painel inicial do GESUAS e clique em '2. Confirmar Login GESUAS' para liberar as buscas.\n"
        })

        while not evento_confirmacao_login.is_set():
            if cancel_event.is_set():
                fila.put({"tipo": "cancelado"})
                return
            time.sleep(0.3)

        fila.put({"tipo": "log", "msg": "\n[GESUAS] Conexão autorizada! Acessando páginas do Edge via CDP...\n"})

        # 5. Execução do cruzamento ativo
        resultados_auditoria = list(historico_auditoria)
        interrompido_pelo_usuario = False

        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp("http://localhost:9222")
            contexto = browser.contexts[0] if browser.contexts else browser.new_context()
            
            # Encontra a página onde o GESUAS está ativo ou usa a primeira
            pagina = None
            for pag in contexto.pages:
                if "gesuas" in pag.url.lower():
                    pagina = pag
                    break
            if not pagina:
                pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

            for indice, (nome_familia, caminho_pdf) in enumerate(familias_alvo.items(), start=1):
                if cancel_event.is_set():
                    interrompido_pelo_usuario = True
                    fila.put({"tipo": "log", "msg": "\n[INTERRUPÇÃO] Parada solicitada. Salvando progresso parcial...\n"})
                    break

                if nome_familia in processados:
                    continue

                fila.put({"tipo": "log", "msg": f"\n[{indice}/{total_familias}] Família: {nome_familia}\n"})
                fila.put({"tipo": "log", "msg": f" -> Documento: {os.path.basename(caminho_pdf)}\n"})

                # --- ETAPA A: Extração dos dados do PDF usando a função nativa do leitor_pdf ---
                cod_fam_pdf, membros_pdf = leitor_pdf.extrair_dados_comprovante_pdf(caminho_pdf)

                dados_pdf = {
                    "codigo_familiar": cod_fam_pdf,
                    "membros": membros_pdf,
                    "pasta_rf": nome_familia
                }

                # Localiza o Responsável Familiar (RF)
                rf_pdf = next((m for m in membros_pdf if m.get("eh_rf")), membros_pdf[0] if membros_pdf else None)
                cpf_rf = rf_pdf.get("cpf_limpo", "") if rf_pdf else ""
                nome_rf = rf_pdf.get("nome_membro", "") if rf_pdf else nome_familia

                fila.put({"tipo": "log", "msg": f" -> Cod. CadÚnico: {cod_fam_pdf or 'N/D'} | RF: {nome_rf} | CPF RF: {cpf_rf or 'Não encontrado'}\n"})

                # --- ETAPA B: Busca no GESUAS via extrator_gesuas ---
                dados_gesuas = {"codigo_familiar_gesuas": "", "membros_gesuas": []}

                if cpf_rf:
                    try:
                        sucesso_busca, motivo_busca = extrator_gesuas.acessar_familia_por_cpf(pagina, cpf_rf)
                        if sucesso_busca:
                            fila.put({"tipo": "log", "msg": " -> Prontuário localizado no GESUAS. Extraindo membros...\n"})
                            dados_gesuas = extrator_gesuas.raspar_composicao_familiar_gesuas(pagina)
                        else:
                            fila.put({"tipo": "log", "msg": f" -> [GESUAS]: Prontuário não acessível ({motivo_busca}).\n"})
                    except Exception as e_busca:
                        fila.put({"tipo": "log", "msg": f" -> [ERRO GESUAS]: {str(e_busca)}\n"})
                else:
                    fila.put({"tipo": "log", "msg": " -> [PULADO GESUAS]: CPF do RF ausente no PDF.\n"})

                # --- EXIBIÇÃO DETALHADA DA COMPOSIÇÃO (CADÚNICO vs GESUAS) ---
                msg_detalhes = "\n" + "  " + "=" * 65 + "\n"

                # 1. Membros do CadÚnico (PDF)
                cod_cad = dados_pdf.get("codigo_familiar", "N/D")
                msg_detalhes += f"  📄 COMPOSIÇÃO CADÚNICO (PDF) [Cód: {cod_cad}]:\n"
                if membros_pdf:
                    for m in membros_pdf:
                        tag_rf = " [RESPONSÁVEL FAMILIAR - RF]" if m.get("eh_rf") else ""
                        msg_detalhes += f"     • {m['nome_membro']} | CPF: {m.get('cpf_formatado', m.get('cpf_limpo', 'N/D'))} | Parentesco: {m.get('parentesco', 'N/D')}{tag_rf}\n"
                else:
                    msg_detalhes += "     • Nenhum membro lido do comprovante.\n"

                # 2. Membros do GESUAS
                cod_ges = dados_gesuas.get("codigo_familiar_gesuas") or "NÃO INFORMADO"
                membros_g = dados_gesuas.get("membros_gesuas", [])
                msg_detalhes += f"\n  🌐 COMPOSIÇÃO GESUAS [Cód: {cod_ges}]:\n"
                if membros_g:
                    for mg in membros_g:
                        par_g = mg.get("parentesco", "")
                        tag_ref = " [PESSOA DE REFERÊNCIA]" if "refer" in par_g.lower() else ""
                        msg_detalhes += f"     • {mg['nome']} | CPF: {mg.get('cpf_formatado', mg.get('cpf_limpo', 'N/D'))} | Parentesco: {par_g}{tag_ref}\n"
                else:
                    msg_detalhes += "     • Prontuário sem membros ou não localizado no GESUAS.\n"

                msg_detalhes += "  " + "=" * 65 + "\n"
                fila.put({"tipo": "log", "msg": msg_detalhes})

                # --- ETAPA C: Reconciliação no motor oficial ---
                resultado_conferencia = auditor_motor.conciliar_familia(dados_pdf, dados_gesuas)
                resultado_conferencia["familia"] = nome_familia
                resultado_conferencia["arquivo_origem"] = os.path.basename(caminho_pdf)
                resultado_conferencia["cpf_rf_buscado"] = cpf_rf
                resultado_conferencia["data_auditoria"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

                resultados_auditoria.append(resultado_conferencia)
                processados.add(nome_familia)

                # Salva o checkpoint atualizado a cada família concluída
                try:
                    with open(caminho_checkpoint, "w", encoding="utf-8") as cp:
                        json.dump({
                            "processados": list(processados),
                            "resultados": resultados_auditoria
                        }, cp, ensure_ascii=False, indent=2)
                except Exception:
                    pass

                # Feedback na barra de progresso
                fila.put({
                    "tipo": "progresso",
                    "val": indice / total_familias,
                    "msg": f" -> Concluído: {resultado_conferencia.get('status', 'Auditado')} ({resultado_conferencia.get('detalhamento', '')})\n"
                })

        # 6. Gravação Final Cronológica e Versionada (Completa ou Parcial)
        if resultados_auditoria:
            carimbo_tempo = datetime.now().strftime("%Y%m%d_%H%M%S")
            sufixo = "_PARCIAL" if interrompido_pelo_usuario else ""
            nome_base = f"Auditoria_{nome_ano_mes}_{carimbo_tempo}{sufixo}"

            # A. Grava planilha Excel na subpasta PLANILHAS_EXCEL
            caminho_excel = os.path.join(pasta_planilhas, f"{nome_base}.xlsx")
            try:
                import pandas as pd
                df = pd.DataFrame(resultados_auditoria)
                cols_ordem = [
                    "familia", "status", "detalhamento", "codigo_familiar_pdf", 
                    "codigo_familiar_gesuas", "total_membros_pdf", "total_membros_gesuas", 
                    "cpf_rf_buscado", "data_auditoria", "arquivo_origem"
                ]
                cols_presentes = [c for c in cols_ordem if c in df.columns] + [c for c in df.columns if c not in cols_ordem]
                df = df[cols_presentes]
                df.to_excel(caminho_excel, index=False)
                fila.put({"tipo": "log", "msg": f"\n[ARQUIVO EXCEL] Gravado em PLANILHAS_EXCEL:\n -> {os.path.basename(caminho_excel)}\n"})
            except Exception as e_df:
                fila.put({"tipo": "log", "msg": f"[AVISO EXCEL]: {str(e_df)}\n"})

            # B. Grava relatório PDF em formato paisagem com NumberedCanvas
            caminho_pdf_final = os.path.join(pasta_relatorios, f"{nome_base}.pdf")
            try:
                lista_formatada_pdf = []
                for r in resultados_auditoria:
                    lista_formatada_pdf.append({
                        "Pasta": r.get("familia") or r.get("pasta_rf", "Não informada"),
                        "Cód. Fam. PDF": r.get("codigo_familiar_pdf", "N/D"),
                        "Cód. Fam. GESUAS": r.get("codigo_familiar_gesuas") or "NÃO INFORMADO",
                        "Membros CadÚnico": r.get("total_membros_pdf", 0),
                        "Membros GESUAS": r.get("total_membros_gesuas", 0),
                        "Status": r.get("status", "Auditado"),
                        "Detalhamento": r.get("detalhamento", "Sem pendências")
                    })

                gerador_relatorio_pdf.gerar_relatorio_pdf(
                    lista_formatada_pdf, 
                    nome_ano_mes, 
                    caminho_pdf_final
                )

                if os.path.exists(caminho_pdf_final):
                    fila.put({"tipo": "log", "msg": f"[ARQUIVO PDF] Gravado em RELATORIOS_PDF:\n -> {os.path.basename(caminho_pdf_final)}\n"})
                else:
                    fila.put({"tipo": "log", "msg": "[AVISO PDF]: Arquivo PDF não encontrado após a compilação.\n"})
            except Exception as e_pdf_gen:
                fila.put({"tipo": "log", "msg": f"[ERRO RELATÓRIO PDF]: Falha ao gerar PDF: {str(e_pdf_gen)}\n"})

        if interrompido_pelo_usuario:
            fila.put({"tipo": "cancelado"})
        else:
            fila.put({"tipo": "log", "msg": f"\n[FINALIZADO] Auditoria completa de {len(processados)} famílias finalizada!\n"})
            fila.put({
                "tipo": "fim_auditoria", 
                "sucesso": True, 
                "pasta_destino": pasta_destino_base
            })

    except Exception as erro:
        fila.put({"tipo": "log", "msg": f"\n[ERRO CRÍTICO NA AUDITORIA]: {str(erro)}\n"})
        fila.put({"tipo": "fim_auditoria", "sucesso": False})
        