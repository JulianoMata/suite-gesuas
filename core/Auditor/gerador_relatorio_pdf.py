# -*- coding: utf-8 -*-
"""
========================================================================================
SUITE GESUAS - CENTRAL DE OPERAÇÕES INTEGRADA (CRAS SUL - CAMPO BELO / MG)
MÓDULO: GERADOR DE RELATÓRIO OFICIAL EM PDF (gerador_relatorio_pdf.py)
AUTORIA: Juliano França da Mata
CARGO: Agente Administrativo / Operador do Cadastro Único - CRAS Sul (Campo Belo/MG)
FORMAÇÃO: Bacharel em Ciência de Dados e Inteligência Artificial | Tecnólogo em Gestão de TI
DESCRIÇÃO: Gera o relatório oficial em orientação paisagem (A4 Landscape) com numeração
            de páginas em duas passagens ('Página X de Y'), consolidação de métricas 
            executivas e tabela detalhada de conformidade CadÚnico x GESUAS.
========================================================================================
"""

import os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """Canvas de duas passagens para numeração precisa de páginas: 'Página X de Y'."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        getattr(self, "_startPage")()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))
        numero_pagina = self.getPageNumber()
        texto_rodape = f"CRAS Sul - Campo Belo/MG | Sistema de Auditoria CadÚnico x GESUAS | Página {numero_pagina} de {page_count}"
        self.drawString(30, 20, texto_rodape)
        emissao = f"Gerado em: {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}"
        self.drawRightString(A4[1] - 30, 20, emissao)
        self.restoreState()

def gerar_relatorio_pdf(lista_resultados: list, nome_mes: str, caminho_saida_pdf: str):
    """Gera o relatório visual em PDF consolidando o diagnóstico da auditoria."""
    doc = SimpleDocTemplate(
        caminho_saida_pdf,
        pagesize=landscape(A4),
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=35
    )

    styles = getSampleStyleSheet()
    
    estilo_titulo = ParagraphStyle(
        'TituloDoc',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#1A365D")
    )
    estilo_subtitulo = ParagraphStyle(
        'SubTituloDoc',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#4A5568")
    )
    estilo_celula_header = ParagraphStyle(
        'CelHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white,
        alignment=1
    )
    estilo_celula = ParagraphStyle(
        'CelCorpo',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#2D3748")
    )
    estilo_celula_pendencia = ParagraphStyle(
        'CelPend',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#C53030")
    )
    estilo_celula_ok = ParagraphStyle(
        'CelOK',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9,
        textColor=colors.HexColor("#22543D")
    )

    elementos = []

    # Cabeçalho Oficial
    elementos.append(Paragraph("PREFEITURA MUNICIPAL DE CAMPO BELO - SECRETARIA DE ASSISTÊNCIA SOCIAL", estilo_subtitulo))
    elementos.append(Paragraph(f"RELATÓRIO DE AUDITORIA E QUALIFICAÇÃO CADASTRAL — MÊS DE REFERÊNCIA: {nome_mes}", estilo_titulo))
    elementos.append(Paragraph("Cruzamento de Consistência entre Comprovantes Oficiais do Cadastro Único e Prontuários do GESUAS", estilo_subtitulo))
    elementos.append(Spacer(1, 12))

    # Indicadores Executivos
    total_auditados = len(lista_resultados)
    total_ok = sum(1 for r in lista_resultados if "OK" in r.get("Status", ""))
    total_pendentes = sum(1 for r in lista_resultados if "INTERVENÇÃO" in r.get("Status", ""))
    total_nao_encontrados = sum(1 for r in lista_resultados if "NÃO ENCONTRADO" in r.get("Status", ""))

    dados_metricas = [
        [
            Paragraph(f"<b>Total de Famílias:</b> {total_auditados}", estilo_celula),
            Paragraph(f"<b>Sincronizadas (OK):</b> <font color='#22543D'><b>{total_ok}</b></font>", estilo_celula),
            Paragraph(f"<b>Requerem Intervenção:</b> <font color='#C53030'><b>{total_pendentes}</b></font>", estilo_celula),
            Paragraph(f"<b>Não Localizadas no GESUAS:</b> <font color='#DD6B20'><b>{total_nao_encontrados}</b></font>", estilo_celula),
        ]
    ]
    tabela_metricas = Table(dados_metricas, colWidths=[190, 190, 190, 210])
    tabela_metricas.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EDF2F7")),
        ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor("#CBD5E0")),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elementos.append(tabela_metricas)
    elementos.append(Spacer(1, 12))

    # Tabela Detalhada de Famílias
    cabecalhos = [
        Paragraph("<b>Família / Munícipe</b>", estilo_celula_header),
        Paragraph("<b>Cód. Fam. (CadÚnico)</b>", estilo_celula_header),
        Paragraph("<b>Cód. Fam. (GESUAS)</b>", estilo_celula_header),
        Paragraph("<b>Membros (Cad / GES)</b>", estilo_celula_header),
        Paragraph("<b>Status da Auditoria</b>", estilo_celula_header),
        Paragraph("<b>Detalhamento Técnico / Ação Recomendada</b>", estilo_celula_header),
    ]

    linhas_tabela = [cabecalhos]
    for r in lista_resultados:
        status_txt = r.get("Status", "")
        estilo_status = estilo_celula_ok if "OK" in status_txt else estilo_celula_pendencia

        linhas_tabela.append([
            Paragraph(str(r.get("Pasta", "")), estilo_celula),
            Paragraph(str(r.get("Cód. Fam. PDF", "")), estilo_celula),
            Paragraph(str(r.get("Cód. Fam. GESUAS", "")), estilo_celula),
            Paragraph(f"{r.get('Membros CadÚnico', 0)} / {r.get('Membros GESUAS', 0)}", estilo_celula),
            Paragraph(status_txt, estilo_status),
            Paragraph(str(r.get("Detalhamento", "")), estilo_celula),
        ])

    tabela_principal = Table(linhas_tabela, colWidths=[150, 95, 95, 75, 115, 250], repeatRows=1)
    tabela_principal.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1A365D")),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor("#E2E8F0")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7FAFC")]),
    ]))
    elementos.append(tabela_principal)

    doc.build(elementos, canvasmaker=NumberedCanvas)
    return caminho_saida_pdf
