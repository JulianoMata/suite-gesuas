# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all
import sys
import os

block_cipher = None

# Inclusão de dados e módulos
datas = [
    ('core', 'core'),
    ('IMAGENS', 'IMAGENS')
]
binaries = []
hiddenimports = [
    'playwright',
    'playwright.sync_api',
    'pandas',
    'openpyxl',
    'reportlab',
    'pdfplumber',
    'pypdf',
    'PIL',
    'PIL.Image',
    'core.Auditor.auditor_engine',
    'core.Auditor.auditor_motor',
    'core.Auditor.extrator_gesuas',
    'core.Auditor.gerador_relatorio_pdf',
    'core.Auditor.leitor_pdf',
    'core.Automacao.automacao_engine',
    'core.Automacao.config',
    'core.Automacao.gesuas_bot',
    'core.Automacao.notificacoes',
    'core.Automacao.relatorio_pdf'
]

# Recursos do CustomTkinter
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]

# Recursos do ReportLab
tmp_rl = collect_all('reportlab')
datas += tmp_rl[0]
binaries += tmp_rl[1]
hiddenimports += tmp_rl[2]

a = Analysis(
    ['app_suite.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtimehooks=[],
    excludes=['IPython', 'zmq', 'jedi', 'pygments'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# =========================================================================
# OPÇÃO 1: EXECUTÁVEL ÚNICO PORTÁTIL (--onefile)
# Ideal para máquinas rápidas (SSD/NVMe) e transporte simples
# =========================================================================
exe_standalone = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Suite_GESUAS_Portatil',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None
)

# =========================================================================
# OPÇÃO 2: VERSÃO DESCOMPACTADA EM PASTA (--onedir)
# Ideal para máquinas com HDD mecânico (arranque imediato sem descompactação)
# =========================================================================
exe_dir = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Suite_GESUAS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None
)

coll = COLLECT(
    exe_dir,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Suite_GESUAS_Diretorio'
)
