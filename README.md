# 🏛️ Suite GESUAS - Central Integrada de Auditoria e Automação Cadastral

> **Vigilância Socioassistencial e Otimização Operacional do Cadastro Único**  
> **CRAS Sul — Prefeitura Municipal de Campo Belo / MG**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/) [![Playwright](https://img.shields.io/badge/RPA-Playwright-orange.svg)](https://playwright.dev/) [![CustomTkinter](https://img.shields.io/badge/GUI-CustomTkinter-2cc985.svg)](https://github.com/TomSchimansky/CustomTkinter) [![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 📌 Visão Geral

A **Suite GESUAS** é uma solução computacional desktop construída para integrar automação robótica de processos (RPA), auditoria de prontuários eletrônicos e inteligência de dados aplicada à assistência social pública municipal. O software atua na convergência entre os formulários físicos/digitais arquivados e a base de dados do sistema **GESUAS** (plataforma de prontuário eletrônico do SUAS).

O ecossistema resolve gargalos crônicos do fluxo técnico do CRAS Sul:

* **Conferência em lote de conformidade cadastral:** Cruzamento automatizado de composições familiares entre os PDFs digitalizados e o banco do GESUAS antes de qualquer manipulação de dados.
* **Auditoria ativa compulsória e lançamentos:** Não realiza *bypass* cego de registros marcados como `"OK"` na planilha; abre ativamente o GESUAS, inspeciona o histórico de atendimentos e valida ou regulariza a existência fidedigna do registro.
* **Saneamento compulsório de Código Familiar em branco:** Inserção automática do Código Familiar de 11 dígitos da planilha quando ausente no prontuário do GESUAS e o munícipe for o Responsável Familiar (RF), respeitando a política de não-regressão.
* **Saneamento ativo em atendimentos de Consulta:** Identificação de divergência ou ausência de Código Familiar no GESUAS com reabertura retroativa do último atendimento para sincronização do código e encerramento normatizado para o RF.
* **Preservação de integridade e auditoria:** Emissão de relatórios analíticos em PDF e Excel com normalização cromática e rastreabilidade explícita de inconsistências e falhas operacionais.

---

## 🔄 Fluxo de Trabalho Recomendado: A Primazia da Auditoria

Para assegurar a governança dos dados e a conformidade com as diretrizes do Ministério do Desenvolvimento e Assistência Social, Família e Combate à Fome (MDS), a operação da Suite GESUAS adota uma hierarquia estrita de execução:

```text
  ┌────────────────────────────────────────────────────────┐
  │ 1. AUDITORIA CADASTRAL PRELIMINAR (Módulo 1: PDFs)     │
  │    - Valida se o prontuário físico/PDF existe          │
  │    - Confere a composição familiar e RF no GESUAS      │
  │    - Aponta inconsistências sem alterar o banco        │
  └───────────────────────────┬────────────────────────────┘
                              │
                              ▼
  ┌────────────────────────────────────────────────────────┐
  │ 2. AUTOMAÇÃO DE LANÇAMENTOS (Módulo 2: Planilha Excel) │
  │    - Varredura ativa total (sem ignorar linhas 'OK')   │
  │    - Audita histórico prévio e previne duplicidade     │
  │    - Lança atendimento e saneia código faltante em RF  │
  │    - Sincroniza Código Familiar e encerra na 3ª opção  │
  └────────────────────────────────────────────────────────┘
```

> **⚠️ Diretriz Operacional:** A execução da **Auditoria Cadastral prévia é mandatória**. Disparar o robô de lançamentos sem a auditoria anterior pode acarretar inserções de atendimentos em prontuários desatualizados, desligados ou com inconsistência estrutural entre a família real e a declarada no sistema.

---

## 🔒 Escopo de Preenchimento e Delimitação Cadastral

Com foco na integridade das informações socioassistenciais e na conformidade com a LGPD, o sistema adota um **escopo rigoroso e normatizado de intervenção**:

### ✅ O que a Suite GESUAS processa e atualiza

* **Auditoria de Histórico sem Bypass:** Toda linha da planilha é aberta e inspecionada no GESUAS, mesmo que já conste como `"OK"` na planilha de trabalho, garantindo que o histórico do prontuário realmente contenha o lançamento.
* **Data e Horário do Atendimento:** Preenchimento estrito com carimbo fidedigno extraído da planilha de trabalho.
* **Vínculo de Atendimento:** Registro padronizado como *"Sem vínculo de serviço"*.
* **Marcação de Visita Domiciliar:** Detecção semântica unificada (nas colunas `SERVICO` e `OBS`) com marcação compulsória de **"Visita Domiciliar"** e **"Busca Ativa"** no formulário de atendimento quando realizada com o Responsável Familiar (RF).
* **Forma de Acesso da Família:**
  * Seleciona compulsoriamente *"Busca Ativa realizada pela equipe da unidade"* caso haja visita domiciliar com o RF.
  * Seleciona *"Por demanda espontânea"* para os demais atendimentos de balcão ou consultas.
* **Saneamento e Não-Regressão de Código Familiar:**
  * **Não-Regressão:** Se o cadastro no GESUAS já possuir um código familiar de 11 dígitos (oriundo de atendimento mais recente), ele é preservado sem sobrescrita.
  * **Saneamento de Campo em Branco:** Se o campo estiver vazio no GESUAS e o munícipe for o **Responsável Familiar (RF)**, a automação insere compulsoriamente o código de 11 dígitos da planilha.
* **Limpeza de Telefones Legados:** Remoção completa de números residenciais/celulares legados desatualizados em *Editar família* para evitar falhas de contato operacional.
* **Encerramento Cirúrgico:** Desmarcação atômica por índice de todas as opções indevidas (como *"Acompanhamento familiar particularizado"*) e seleção exclusiva da 3ª opção: **"Cadastramento/Atualização Cadastral na GESUAS"**.

### ⛔ Campos NÃO modificados pela automação (Intervenção Humana Exclusiva)

* **Condição de Deficiência (PcD):** Informações sobre existência de deficiência nos membros familiares, laudos ou necessidades especiais permanecem intocadas, exigindo comprovação documental e declaração assistida.
* **Endereço e Local de Residência:** Preservados intactos para não descaracterizar territórios de abrangência ou microáreas de PSF.
* **Renda e Informações Financeiras:** Nenhum cálculo de renda per capita ou remuneração de membros é alterado.
* **Escolaridade e Ocupação:** Variáveis pedagógicas e de qualificação profissional mantêm-se exatamente como digitadas pelos operadores técnicos.
* **Composição e Parentesco:** O robô não altera vínculos de parentesco prévios de famílias estruturadas no sistema.

---

## ⚙️ Regras de Negócio e Funcionalidades Centrais

### 1. Auditoria Ativa de Atendimentos (Sem Bypass de "OK")

* **Auditoria Compulsória:** O robô não pula linhas sinalizadas como `"OK"` na planilha. Ele pesquisa a pessoa no sistema, abre o histórico em *Editar um Atendimento* e audita ativamente a existência do registro na data e hora especificadas.
* **Recuperação de Omissões:** Caso a planilha indique `"OK"`, mas o atendimento não seja localizado no prontuário, a automação sinaliza `[AUDITORIA]`, efetua o lançamento retroativo pendente e registra a divergência no diagnóstico.

### 2. Saneamento Compulsório de Código Familiar em Branco

* Durante a navegação em *Editar família* (seja em checagem de atendimento existente, saneamento de consulta ou novo atendimento):
  * Se o campo no GESUAS estiver em branco ou incompleto e a planilha fornecer um código válido de 11 dígitos:
    * **Munícipe é RF:** O código é digitado e gravado no cadastro da família.
    * **Munícipe é Dependente:** O código não é alterado, evitando a vinculação indevida de chaves em prontuários compartilhados.

### 3. Conexão Acoplada via CDP (Chrome DevTools Protocol)

* **Login pelo Operador:** O sistema inicializa uma sessão do Microsoft Edge conectada via porta `9222` (`--remote-debugging-port=9222`), permitindo que o operador realize seu login convencional no GESUAS manualmente antes de liberar a execução do robô.
* **Resiliência e Desacoplamento:** Elimina credenciais embutidas em código e dispensa a recriação contínua de perfis. Preparado para autenticações por MFA ou Gov.br.

### 4. Tratamento Especial de Visita Domiciliar e Edição Retroativa

* O sistema verifica termos como `VISITA`, `DOMICILI`, `DOMICILIO` ou `ENTREVISTA DOMICILIAR` tanto no serviço quanto nas observações (`OBS`).
* **Atendimento já existente no histórico:** O robô clica em *Editar* na linha correspondente da data, marca *Visita Domiciliar* e *Busca Ativa*, confirma no botão *Iniciar*, ajusta Forma de Acesso e Código Familiar em *Editar família* e encerra na 3ª opção.

### 5. Saneamento Inteligente em Atendimentos de CONSULTA

* Se o munícipe for o **Responsável Familiar (RF)** e houver Código Familiar válido (11 dígitos) na planilha:
  * Extrai o código da tela do GESUAS;
  * **Se divergir ou faltar:** Abre o histórico, reabre o atendimento mais recente via *Iniciar*, acessa *Editar família*, atualiza o código, limpa telefones, define Demanda Espontânea e encerra na 3ª opção.
* **Consultas sem Código Familiar (Excluídos / Orientações):** Trata registros sem código de 11 dígitos (munícipes excluídos ou orientações em balcão), registrando o status de consulta e a observação no relatório sem alterar o banco indevidamente.

### 6. Política de Não-Regressão e Resolução de Alertas no DOM

* **Preservação de Dados Recentes:** Caso o prontuário no GESUAS já possua um código familiar de 11 dígitos consolidado em atendimentos posteriores ao mês trabalhado, o código existente é mantido.
* **Captura de Conflito de Duplicidade:** Caso o GESUAS emita alerta modal de código familiar já cadastrado em outro prontuário, o robô captura o aviso, fecha a modal, cancela a janela de edição e desobstrui as camadas de bloqueio de ponteiro (`ui-widget-overlay`), prevenindo travamentos por timeout.

### 7. Rastreabilidade e Diagnóstico Explícito de Falhas

* Qualquer intercorrência operacional durante a execução (como munícipe não localizado, munícipe desligado, erro de carregamento ou falha no encerramento) é interceptada via bloco `try/except` seguro.
* O erro é catalogado explicitamente com status `"ERRO"` ou mensagem descritiva no campo de diagnóstico da planilha de auditoria e do relatório oficial em PDF.

### 8. Normalização Cromática no Relatório PDF

* O compilador ReportLab (`relatorio_pdf.py`) utiliza funções de normalização Unicode (`NFKD`), eliminando divergências entre strings acentuadas (`INCLUSÃO` vs `INCLUSAO`, `EXCLUSÃO` vs `EXCLUSAO`).
* Todas as linhas da tabela recebem estilização cromática padronizada conforme a legenda, impedindo que linhas de atendimento fiquem em branco por falha de correspondência de caracteres.

---

## 🖥️ Interface do Usuário

A interface foi projetada com o framework **CustomTkinter** com alternador dinâmico de tema (*Dark Mode* / *Light Mode*) e janela modal de Guia Operacional integrada no cabeçalho:

| 🔍 Módulo 1: Auditoria Cadastral (PDFs vs GESUAS) | 🤖 Módulo 2: Robô de Lançamentos (Planilhas Excel) |
| :---: | :---: |
| ![Auditoria Cadastral](IMAGENS/aba_auditoria.png) | ![Robô de Lançamentos](IMAGENS/aba_automacao.png) |
| *Varredura e validação cronológica de prontuários digitalizados com checkpoints de lote.* | *Processamento em lote de atendimentos com auditoria ativa, anti-duplicidade e saneamento.* |

---

## 📂 Estrutura do Repositório

```text
SUITE_GESUAS/
│
├── core/                           # Núcleo de processamento e motores do sistema
│   ├── Auditor/                    # Módulo 1: Auditoria Cadastral (PDFs vs GESUAS)
│   │   ├── __init__.py             # Inicializador do pacote
│   │   ├── auditor_engine.py       # Orquestrador da auditoria e despacho de eventos
│   │   ├── auditor_motor.py        # Motor lógico e regras de matching cadastral
│   │   ├── extrator_gesuas.py      # Inspeção de tela e busca no prontuário GESUAS
│   │   ├── gerador_relatorio_pdf.py# Compilador ReportLab (NumberedCanvas / Paisagem)
│   │   └── leitor_pdf.py           # Parser e extração textual de formulários PDF
│   │
│   ├── Automacao/                  # Módulo 2: Robô de Lançamentos (Planilhas Excel)
│   │   ├── __init__.py             # Inicializador do pacote
│   │   ├── automacao_engine.py     # Motor operacional com auditoria ativa e saneamento
│   │   ├── config.py               # Definições de portas, perfis e parâmetros locais
│   │   ├── gesuas_bot.py           # Procedimentos CLI e manipulação de formulários
│   │   ├── notificacoes.py         # Tratamento de diálogos e alertas visuais
│   │   └── relatorio_pdf.py        # Relatório de atendimentos com normalização cromática
│   │
│   └── __init__.py                 # Pacote raiz do core
│
├── IMAGENS/                        # Capturas de tela da interface gráfica
│   ├── aba_auditoria.png           # Captura da interface do Módulo de Auditoria
│   └── aba_automacao.png           # Captura da interface do Robô de Lançamentos
│
├── .gitattributes                  # Controle de finais de linha (LF/CRLF) e binários
├── .gitignore                      # Filtro para LGPD, dados sensíveis e arquivos transitórios
├── app_suite.py                    # Interface gráfica unificada (CustomTkinter Multithread)
├── LICENSE                         # Licença MIT
├── README.md                       # Documentação técnica e operacional
├── requirements.txt                # Dependências externas do ecossistema Python
└── Suite_GESUAS.spec               # Especificação de compilação dual (Portátil e Diretório)
```

---

## 🗂️ Diretórios Gerados Dinamicamente em Tempo de Execução

As pastas de armazenamento de resultados **não integram o versionamento estático** do Git (sendo filtradas via `.gitignore` para resguardo de dados pessoais conforme a LGPD):

| Diretório Gerado | Finalidade Operacional |
| :--- | :--- |
| `PLANILHAS_EXCEL/` | Armazena a cópia sincronizada da planilha com status `OK` preenchido (`CADASTRO_ATUALIZADO_[MÊS]_[TIMESTAMP].xlsx`) e o relatório analítico em formato de planilha. A planilha de entrada original nunca é sobrescrita. |
| `RELATORIOS_PDF/` | Recebe os relatórios oficiais formatados em PDF (paisagem), contendo métricas executivas consolidadas, totalizadores por tipo de serviço e estilização cromática blindada. |
| `CHECKPOINTS/` | Registra arquivos temporários (`.json`) com o progresso do lote auditado. Permite pausar e retomar lotes volumosos de onde pararam ou reiniciar do início sob demanda. |

---

## 🛠️ Tecnologias e Bibliotecas

* **Python 3.10+** (64 bits)
* **CustomTkinter:** Framework moderno de componentes GUI com suporte a temas e redimensionamento responsivo.
* **Playwright:** Controle e inspeção do navegador via protocolo CDP.
* **Pandas & OpenPyXL:** Leitura, manipulação de matrizes de dados e exportação de planilhas Excel com tipagem protegida.
* **ReportLab:** Mecanismo vetorial de compilação de PDFs com numeração de páginas em duas passagens (`NumberedCanvas`).
* **PDFPlumber:** Extração de texto e metadados a partir dos comprovantes digitais.

---

## 🚀 Como Executar o Projeto

### 1. Clonar o Repositório

```powershell
git clone https://github.com/SEU_USUARIO/SUITE_GESUAS.git
cd SUITE_GESUAS
```

### 2. Configurar o Ambiente Virtual

```powershell
python -m venv .venv
.\.venv\Scripts\activate
```

### 3. Instalar Dependências

```powershell
pip install -r requirements.txt
playwright install chromium
```

### 4. Inicializar a Aplicação

```powershell
python app_suite.py
```

---

## 📦 Estratégia de Distribuição e Empacotamento Dual

Para atender à diversidade do parque tecnológico dos órgãos públicos, a Suite GESUAS conta com uma especificação do PyInstaller (`Suite_GESUAS.spec`) que gera duas modalidades de saída simultaneamente:

1. **`dist/Suite_GESUAS_Portatil.exe` (`--onefile`):**
   * **Perfil:** Arquivo único portátil.
   * **Recomendação:** Computadores modernos com armazenamento SSD/NVMe ou para transporte rápido em pendrives.
   * **Comportamento:** Descompacta temporariamente as dependências na inicialização em `%TEMP%`.
2. **`dist/Suite_GESUAS_Diretorio/` (`--onedir`):**
   * **Perfil:** Pasta independente de execução direta com atalho para `Suite_GESUAS.exe`.
   * **Recomendação:** Computadores com disco rígido mecânico (HDD convencional) e máquinas de desempenho modesto.
   * **Comportamento:** Abertura imediata em 1 a 2 segundos, eliminando a sobrecarga de descompactação e a retenção por varredura contínua de antivírus.

### Como gerar ambas as versões

Com o ambiente virtual ativado no terminal:

```powershell
pyinstaller Suite_GESUAS.spec
```

Os resultados estarão prontos para uso no diretório `dist/`.

---

## 👨‍💼 Autoria e Lotação Institucional

* **Autor:** Juliano França da Mata  
* **Cargo:** Agente Administrativo / Operador do Cadastro Único  
* **Lotação:** CRAS Sul — Prefeitura Municipal de Campo Belo / MG  
* **Contato:** `jfmatta@gmail.com`  
* **Qualificação Técnica e Acadêmica:**  
  * Bacharel em Ciência de Dados e Inteligência Artificial (UniDomBosco)  
  * Tecnólogo em Gestão de Tecnologia da Informação (UniCesumar)  
  * Técnico em Informática  

---

## 📜 Licença

Este projeto é distribuído sob os termos da licença [MIT](LICENSE)
