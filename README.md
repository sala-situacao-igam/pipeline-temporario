# Pipeline de Ingestão e Indicadores Hidrometeorológicos — ANA/HidroWEB (IGAM)

Pipeline automatizado para ingestão diária incremental de dados hidrometeorológicos de estações telemétricas da ANA (Agência Nacional de Águas e Saneamento Básico), via plataforma HidroWEB, com tratamento, controle de qualidade e cálculo de indicadores de desempenho do contrato de gestão com o IGAM.

> Repositório privado. Contém lógica de acesso a dados institucionais — não distribuir nem tornar público sem autorização.

## Objetivo

- Ingerir diariamente, de forma incremental (sem reprocessar histórico), os dados de estações telemétricas (fluviométricas e pluviométricas) via API da ANA.
- Tratar e padronizar os dados (tipagem, remoção de outliers/códigos de erro, deduplicação).
- Armazenar os dados por estação em CSV, hospedados no Google Drive.
- Calcular e consolidar os indicadores de desempenho do contrato de gestão (grupos 2.x e 4.x).
- Publicar um dashboard de acompanhamento compartilhável com o IGAM e a PM do projeto.

## Indicadores cobertos

| Indicador | Descrição | Status |
|---|---|---|
| 2.1 | % de transmissão de dados sem atraso | Bloqueado até migrar para a API HidroWebService nova (acesso pendente) |
| 2.2 | % de transmissão de dados sem perda de registros | **Concluído** — pontuação por estação, dashboard publicado |
| 2.8 | % de dados consistidos | Em desenvolvimento — teste de range com janela expansível pendente |
| 4.1 | % de previsões do tempo publicadas | **Concluído** — extração do SIMGE testada com dado real |
| 4.2 | % de monitoramento meteorológico e envio de alertas | **Concluído** — Fonte é registro manual (WhatsApp) — caminho de rastreio (Forms) em decisão |
| 4.3 | % de monitoramento climático realizado | **Concluído** — extração do SIMGE testada com dado real |
| 4.6 | % de produtos hidrometeorológicos elaborados | Fonte de dados pendente de confirmação |

## Arquitetura (visão geral)

- **Fontes de dados:**
  - API da ANA (`telemetriaws1.ana.gov.br`) — dado bruto de estação (chuva/cota/vazão). *(Nota: o nome "HidroWebService" às vezes aparece em comentários antigos se referindo a essa API atual, por engano — esse é o nome da API **nova**, ainda não migrada.)*
  - Site do SIMGE (`simge.mg.gov.br`) — documentos publicados (previsões do tempo e boletins de tendência climática), usados pelos indicadores 4.1/4.3.
- **Armazenamento:** Google Drive, via conta de serviço do Google Cloud (sem interação manual/OAuth). IDs de todas as pastas ficam centralizados em `config.py`.
- **Execução diária (produção):** GitHub Actions, em **dois workflows separados** desde 31/08/2026 — `pipeline_diario_hidro.yml` (ingestão ANA + qualidade + dashboard do indicador 2.2) e `pipeline_diario_meteoro.yml` (extração SIMGE + página de indicadores 4.1/4.3), cada um com seu próprio agendamento e disparo manual (aba Actions). Separados de propósito: a extração do SIMGE depende de raspar um portal que já mudou de estrutura uma vez sem aviso — se isso quebrar de novo, só a rodada de meteorologia falha, hidrometria continua rodando normalmente.
- **Processamento:** Python + pandas + matplotlib (para os PNGs de relatório).
- **Dashboard principal:** site estático (HTML puro, sem backend), publicado no repositório público `dashboard-igam` via GitHub Pages — https://vdlapc.github.io/dashboard-igam/. Duas páginas: Hidrometria (`index.html`, indicador 2.2) e Meteorologia (`meteorologia.html`, indicadores 4.1/4.3), cada uma publicada pelo seu próprio workflow, com navegação entre as duas (injetada automaticamente por `nav_site.py` em cada rodada).
- **Dashboard alternativo (standby):** exportação para Planilha Google, pronta para alimentar o Google Looker Studio caso seja necessário no futuro — mantida em paralelo, não é o principal hoje.

## Estrutura de pastas no Google Drive

```
Operacional > Hidrometria
  ├── Frentes - Telemetria        (listas de estações por frente, mantidas pela equipe)
  └── automacao                   (compartilhada com a conta de serviço)
        ├── data/
        │     └── frente1.csv     (lista de estações em uso pelo pipeline)
        ├── estacoes/
        │     └── estacao_<codigo>.csv   (um arquivo por estação, atualizado incrementalmente)
        └── relatorios/
              ├── dim_estacao.csv                  (dimensão -- cadastro por estação, mantida
              │                                      manualmente pela Valéria, fora do pipeline)
              ├── dim_tempo.csv                     (dimensão -- calendário 2014-2034, gerada 1x)
              ├── fato_disponibilidade.csv          (fato -- disponibilidade por estação x dia,
              │                                      base do indicador 2.2)
              ├── fato_consistencia.csv             (fato -- resultado dos testes de qualidade)
              ├── relatorio_indicador_2_2.csv        (snapshot -- pontuação atual por estação,
              │                                      ver nota de modelagem abaixo)
              ├── indicadores_diarios.csv
              ├── log_erros.csv
              └── log_cargas_iniciais.csv
```

Além dessa árvore, existem 3 pastas de saída específicas dos indicadores 4.x/relatórios, cujos IDs ficam em `config.py`: `PASTA_PREVISAO_TEMPO_ID` (CSVs do 4.1), `PASTA_MONITORAMENTO_CLIMATICO_ID` (CSVs do 4.3) e `PASTA_GRAFICOS_ID` (PNGs + páginas HTML geradas por `gerar_relatorios_visuais.py`).

### Modelagem de dados (Fatos e Dimensões) -- desde 01/09/2026

Os arquivos da pasta `relatorios/` seguem o padrão Fato/Dimensão: `dim_estacao.csv` (cadastro de cada estação -- código, nome, coordenadas, `tem_chuva`/`tem_cota`/`tem_vazao`, `ano_inicio_operacao`) e `dim_tempo.csv` (calendário) são as dimensões; `fato_disponibilidade.csv` e `fato_consistencia.csv` são os fatos (grão estação x dia). `dim_estacao.csv` é mantido manualmente pela Valéria (não existe script automático que o gera/atualiza -- decisão de 01/09, ver histórico de commits) -- ao adicionar uma frente nova, as colunas cadastrais são copiadas do `frenteN.csv` e as colunas calculadas (`tem_chuva`/`tem_cota`/`tem_vazao`/`ano_inicio_operacao`) precisam ser preenchidas a partir do histórico real da estação nova. `relatorio_indicador_2_2.csv` continua fora desse padrão de propósito: é um snapshot ("a pontuação calculada agora, considerando todo o histórico até este momento"), não um fato histórico com `data_calculo` -- decisão da Valéria, para não adicionar complexidade que o indicador não precisa.

## Estrutura do repositório

Todo módulo é um único arquivo `.py` direto na raiz do repositório (sem subpastas) — mais simples de importar (`import drive_io`, `import orquestrador` etc.) sem montar um pacote Python formal. A única pasta obrigatória é a do GitHub Actions, porque ele exige esse caminho exato para encontrar o workflow.

O agrupamento abaixo é só uma forma de ORIENTAÇÃO (nenhum arquivo mudou de lugar) — pense nele como um mapa de "o que cada script faz", separado pelo papel de cada um no pipeline: ingestão → qualidade → cálculo dos indicadores → visualização → orquestração.

```
pipeline-hidroweb-igam/
  │
  ├── CONFIGURAÇÃO / INFRAESTRUTURA
  │     ├── config.py                              # IDs de todas as pastas do Google Drive usadas no projeto
  │     ├── drive_io.py                             # todo o acesso ao Drive: ler/salvar CSV, Parquet, Planilha
  │     │                                           #   Google, e arquivo genérico (PNG/HTML, via salvar_arquivo())
  │     ├── requirements.txt                        # dependências Python
  │     ├── .github/workflows/pipeline_diario_hidro.yml    # agendamento diário -- hidrometria
  │     └── .github/workflows/pipeline_diario_meteoro.yml  # agendamento diário -- meteorologia
  │
  ├── INGESTÃO  (buscar o dado bruto numa fonte externa)
  │     ├── ingestao_ana.py                         # consulta à API da ANA (1 estação por vez)
  │     └── extrair_documentos_simge_ingestao.py     # extrai os documentos publicados no site do SIMGE
  │                                                  #   (raspagem do portal Liferay) -- separado do CÁLCULO
  │                                                  #   dos indicadores 4.1/4.3 desde 31/08 (ver "ANÁLISE")
  │
  ├── QUALIDADE  (testes que aprovam/reprovam cada leitura, indicador 2.8)
  │     ├── etapa01_teste_precipitacao_range.py       # teste de range (mín/máx histórico da própria estação)
  │     │                                             #   -- reimplementação com janela expansível PENDENTE
  │     ├── etapa02_step.py                          # teste de salto brusco entre leituras consecutivas
  │     ├── etapa03_persist.py                        # teste de valor "travado" (persistência)
  │     └── etapa04_lacunas.py                        # disponibilidade/lacunas de chuva, cota e vazão --
  │                                                   #   é a base do fato_disponibilidade.csv (indicador 2.2).
  │                                                   #   Desde 01/09 NÃO calcula mais tem_chuva/tem_cota/
  │                                                   #   tem_vazao (isso virou atributo de dim_estacao.csv)
  │
  ├── ANÁLISE  (cálculo dos indicadores a partir do dado já tratado)
  │     ├── indicador_2_2_calculo.py                  # calcular_pontuacao_2_2() -- pontuação 0-10 por estação
  │     │                                             #   (Anexo II) -- separado da geração de HTML desde 31/08
  │     │                                             #   (ver "VISUALIZAÇÃO"). Desde 01/09 recebe fato_
  │     │                                             #   disponibilidade + dim_estacao (faz merge por
  │     │                                             #   codigo_estacao pra saber tem_cota/ano_inicio_operacao)
  │     └── extrair_documentos_simge_calculo.py        # contar_previsoes_4_1() / contar_tendencia_climatica_4_3()
  │                                                    #   -- calculam os indicadores 4.1/4.3 a partir dos
  │                                                    #   documentos já extraídos por extrair_documentos_simge_ingestao.py
  │
  ├── VISUALIZAÇÃO  (site + imagens para relatório em PDF)
  │     ├── indicador_2_2_html.py                      # gerar_html_2_2() -- dashboard HTML da Hidrometria (2.2)
  │     ├── indicador_meteorologia.py                  # gerar_html_meteorologia() -- página HTML da Meteorologia
  │     │                                             #   (4.1/4.3)
  │     ├── nav_site.py                                # barra de navegação entre as 2 páginas -- injetada
  │     │                                             #   automaticamente por rodar_diario_hidro.py/
  │     │                                             #   rodar_diario_meteoro.py em cada rodada de produção
  │     ├── exportar_imagem_indicador_2_2.py            # PNGs do indicador 2.2 para relatório em PDF (heatmap,
  │     │                                             #   barras por faixa, barras por estação)
  │     └── exportar_imagem_indicador_meteorologia.py   # PNGs dos indicadores 4.1/4.3 para relatório em PDF
  │                                                    #   (barras por dia da semana, barras por mês)
  │
  └── ORQUESTRAÇÃO  (rodar tudo em sequência -- agora em 2 pipelines de produção separados)
        ├── orquestrador.py                          # roda a ingestão (ingestao_ana) para todas as estações
        ├── pipeline_consistencia.py                  # roda os 4 testes de qualidade para todas as estações
        ├── rodar_diario_hidro.py                     # PONTO DE ENTRADA do pipeline_diario_hidro.yml -- ingestão
        │                                             #   + qualidade + indicador 2.2 + publicação do index.html
        │                                             #   (com navegação), tudo numa rodada de hidrometria
        ├── rodar_diario_meteoro.py                   # PONTO DE ENTRADA do pipeline_diario_meteoro.yml -- extração
        │                                             #   SIMGE (4.1/4.3) + publicação do meteorologia.html
        │                                             #   (com navegação), rodada separada de meteorologia
        └── gerar_relatorios_visuais.py                # roda a parte de VISUALIZAÇÃO (2.2 + 4.1/4.3 + os PNGs
                                                        #   de relatório) de ponta a ponta, para uso manual/Colab
                                                        #   -- os PNGs continuam só aqui, não entram nas rodadas
                                                        #   automáticas acima
```

**Separação dos dois arquivos que eram "híbridos" (concluída em 31/08/2026):** `indicador_2_2.py` (misturava cálculo + geração de HTML) virou `indicador_2_2_calculo.py` + `indicador_2_2_html.py`; `extrair_documentos_simge.py` (misturava ingestão + cálculo) virou `extrair_documentos_simge_ingestao.py` + `extrair_documentos_simge_calculo.py`. Os dois arquivos antigos foram removidos do repositório. Nenhuma lógica mudou nessa separação, só o arquivo onde cada função mora — testado de ponta a ponta (com dado fictício e, depois, com as duas rodadas de produção reais) antes de entrar em produção. Os imports em todos os arquivos que dependiam deles (`rodar_diario_hidro.py`, `rodar_diario_meteoro.py`, `gerar_relatorios_visuais.py`, `exportar_imagem_indicador_2_2.py`, `exportar_imagem_indicador_meteorologia.py`, `nav_site.py`) já foram atualizados.

**Renomeação para o padrão Fato/Dimensão (01/09/2026):** `relatorio_disponibilidade.csv` virou `fato_disponibilidade.csv` e `relatorio_consistencia.csv` virou `fato_consistencia.csv` (mesmas colunas e lógica de upsert, só nome do arquivo no Drive). `etapa04_lacunas.py` deixou de calcular/devolver `tem_chuva`/`tem_cota`/`tem_vazao` (V6) -- essas 3 colunas viraram atributo do `dim_estacao.csv`, criado nesta mesma data. `indicador_2_2_calculo.calcular_pontuacao_2_2()` (V4) passou a receber `fato_disponibilidade` **e** `dim_estacao` (faz merge por `codigo_estacao` para saber `tem_cota`/`ano_inicio_operacao`, em vez de calcular isso do fato) -- se uma estação existir no fato mas ainda não estiver cadastrada no `dim_estacao.csv`, a função levanta um erro claro em vez de gerar dado incorreto silenciosamente. Testado de ponta a ponta com dado fictício (incluindo o caso de estação ausente da dimensão) antes de entrar em produção. Scripts atualizados: `etapa04_lacunas.py`, `indicador_2_2_calculo.py`, `pipeline_consistencia.py`, `rodar_diario_hidro.py`, `gerar_relatorios_visuais.py`, `exportar_imagem_indicador_2_2.py`, `drive_io.py` (docstring). `orquestrador.py` **não** foi alterado -- continua lendo `frenteN.csv` bruto diretamente, não `dim_estacao.csv` (evita dependência circular: a ingestão não precisa das colunas calculadas da dimensão). As Planilhas Google que alimentam o Looker Studio também foram renomeadas nesta mesma data (`relatorio_disponibilidade_dashboard` → `fato_disponibilidade_dashboard`, `relatorio_consistencia_dashboard` → `fato_consistencia_dashboard`, em `pipeline_consistencia.py`) — confirmado com a Valéria que elas ainda não estavam conectadas a nenhum relatório do Looker Studio, então não havia risco de quebrar uma conexão existente. As planilhas antigas ficam paradas no Drive (podem ser apagadas manualmente quando quiser).

## Pré-requisitos de configuração

1. Projeto no Google Cloud com a API do Google Drive habilitada.
2. Conta de serviço do Google Cloud com acesso de Editor à pasta `automacao` no Drive.
3. Chave JSON da conta de serviço armazenada como Secret no GitHub Actions (nunca commitada no repositório).

## Autoria

Valéria Dallapícula — automação de dados hidrometeorológicos.
