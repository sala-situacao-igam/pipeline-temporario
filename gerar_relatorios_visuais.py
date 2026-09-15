"""
Descrição: script manual (Colab) que gera os gráficos/páginas dos
indicadores 2.1, 2.2, 4.1, 4.2 e 4.3 e salva tudo na pasta de gráficos do
Drive (config.PASTA_GRAFICOS_ID). Não tem função definida -- roda direto,
de cima para baixo, em 4 passos.

Conexões do Pipeline:
- Entradas: config.py, drive_io.py, indicador_2_1_calculo.py,
  exportar_imagem_indicador_2_1.py, indicador_2_1_html.py,
  indicador_2_2_calculo.py, indicador_2_2_html.py,
  exportar_imagem_indicador_2_2.py, extrair_documentos_simge_ingestao.py,
  extrair_documentos_simge_calculo.py, indicador_meteorologia.py,
  exportar_imagem_indicador_meteorologia.py, nav_site.py;
  fato_disponibilidade.csv, dim_estacao.csv e os
  estacao_detalhada_XXXXXXXX.csv (config.PASTA_TELEMETRIA_DETALHADA_ID) do
  Drive.
- Saídas: index.html (2.1 + 2.2, 2.1 acima), meteorologia.html e 6 PNGs,
  salvos localmente e na pasta de gráficos do Drive
  (config.PASTA_GRAFICOS_ID) -- é esse PASSO 4 que efetivamente sobe os
  arquivos pro Drive; os exportar_imagem_*.py só salvam localmente. Não
  publica no GitHub Pages -- isso continua manual (GitHub Desktop).

Funções: nenhuma (script sequencial).

Como usar no Colab: cole este arquivo inteiro numa única célula (ou rode
`%run gerar_relatorios_visuais.py` se ele estiver na mesma pasta que os
outros .py do repositório) e execute uma vez, de cima pra baixo.

O que este script faz, em ordem:
  PASSO 1 -- conecta no Drive
  PASSO 2 -- indicadores 2.1 e 2.2 (Hidrometria): le os relatorios, calcula
             a pontuacao dos dois, gera os PNGs (2.1: comparacao 64x44;
             2.2: barras_faixa) e o index.html (2.1 acima do 2.2, mesma
             pagina)
  PASSO 3 -- indicadores 4.1/4.2/4.3 (Meteorologia): extrai do SIMGE,
             gera o meteorologia.html E os 4 PNGs (4.1: barras por dia
             da semana; 4.2: barras por mes dos dias-com-alerta e dos
             alertas individuais; 4.3: barras por mes)
  PASSO 4 -- salva os 8 arquivos gerados (6 PNGs + 2 HTMLs) na pasta de
             graficos do Drive (config.PASTA_GRAFICOS_ID)

"""

import config
import drive_io

# ============================================================
# PASSO 1 -- conectar no Drive
# ============================================================
print("PASSO 1 -- conectando no Drive...")
servico = drive_io.conectar_drive("chave_servico.json")  # troque pelo nome real do seu arquivo de chave, se for diferente
print("Conectado.\n")


# ============================================================
# PASSO 2 -- indicadores 2.1 e 2.2 (Hidrometria): pontuacao, graficos e index.html
# ============================================================
print("PASSO 2 -- indicadores 2.1 e 2.2 (Hidrometria)...")

from indicador_2_1_calculo import (
    carregar_universo_64,
    carregar_pacotes_telemetria_detalhada,
    calcular_cd_2_1,
)
from exportar_imagem_indicador_2_1 import exportar_comparacao_2_1
from indicador_2_1_html import gerar_cartao_2_1_html
from indicador_2_2_calculo import calcular_pontuacao_2_2
from indicador_2_2_html import gerar_html_2_2
from exportar_imagem_indicador_2_2 import exportar_barras_faixa_2_2
from nav_site import injetar_nav

fato_disponibilidade = drive_io.ler_csv(servico, "fato_disponibilidade.csv", config.PASTA_RELATORIOS_ID)
dim_estacao = drive_io.ler_csv(servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID)
df_pontuacao = calcular_pontuacao_2_2(fato_disponibilidade, dim_estacao)

exportar_barras_faixa_2_2(df_pontuacao, "indicador_2_2_barras_faixa.png")

# -- indicador 2.1: mesma pagina do 2.2, mas entra ACIMA dele --
estacoes_64 = carregar_universo_64(servico)
df_pacotes = carregar_pacotes_telemetria_detalhada(servico, config.PASTA_TELEMETRIA_DETALHADA_ID)
estacoes_44 = sorted(df_pacotes["codigo_estacao"].unique().tolist())

# dias_periodo calculado a partir do intervalo real dos dados (a API nova
# devolve uma janela ~30 dias, mas nao necessariamente 30 exatos todo dia)
data_min = df_pacotes["Data_Hora_Medicao"].min()
data_max = df_pacotes["Data_Hora_Medicao"].max()
dias_periodo = (data_max.normalize() - data_min.normalize()).days + 1

resultado_64 = calcular_cd_2_1(df_pacotes, estacoes_64, dias_periodo=dias_periodo)
resultado_44 = calcular_cd_2_1(df_pacotes, estacoes_44, dias_periodo=dias_periodo)
periodo_texto = f"Período considerado: {data_min:%d/%m/%Y} a {data_max:%d/%m/%Y}"

exportar_comparacao_2_1(resultado_64, resultado_44, periodo_texto, "indicador_2_1_comparacao_64_44.png")
cartao_2_1_html = gerar_cartao_2_1_html(resultado_64, resultado_44, periodo_texto)

gerar_html_2_2(df_pontuacao, "index.html", cartao_2_1_html=cartao_2_1_html)
injetar_nav("index.html", "hidrometria")

print("PASSO 2 concluido: 2 PNGs (2.1 + 2.2) + index.html (2.1 acima do 2.2) gerados.\n")


# ============================================================
# PASSO 3 -- indicadores 4.1/4.2/4.3 (Meteorologia): SIMGE + meteorologia.html
# ============================================================
print("PASSO 3 -- indicadores 4.1/4.2/4.3 (Meteorologia)...")

from datetime import date
from extrair_documentos_simge_ingestao import (
    URL_PASTA_PREVISOES_2026,
    URL_PASTA_TENDENCIA_CLIMATICA_2026,
    URL_ALERTAS_TEMPESTADE_SEVERA,
)
from extrair_documentos_simge_calculo import (
    contar_previsoes_4_1,
    contar_tendencia_climatica_4_3,
    contar_alertas_4_2,
    calcular_cd_4_1,
    calcular_cd_4_3,
    calcular_cd_4_2,
)
from indicador_meteorologia import gerar_html_meteorologia
from exportar_imagem_indicador_meteorologia import (
    exportar_barras_dia_semana_4_1,
    exportar_barras_mes_4_3,
    exportar_barras_dias_alerta_4_2,
    exportar_barras_alertas_individuais_4_2,
)

data_inicio = "2026-01-01"
hoje = date.today()

r_4_1 = contar_previsoes_4_1(URL_PASTA_PREVISOES_2026, data_inicio, hoje)
r_4_3 = contar_tendencia_climatica_4_3(URL_PASTA_TENDENCIA_CLIMATICA_2026, data_inicio, hoje)
r_4_2 = contar_alertas_4_2(URL_ALERTAS_TEMPESTADE_SEVERA, data_inicio, hoje)  # novo (02/09)
cd_4_1 = calcular_cd_4_1(r_4_1, data_inicio, hoje)  # (02/09) -- pontuação (CD) do 4.1
cd_4_3 = calcular_cd_4_3(r_4_3, data_inicio, hoje)  # novo (02/09) -- pontuação (CD) do 4.3
cd_4_2 = calcular_cd_4_2(r_4_2, data_inicio, hoje)  # novo (02/09) -- pontuação (CD) do 4.2

gerar_html_meteorologia(
    r_4_1, r_4_3, "meteorologia.html",
    resultado_cd_4_1=cd_4_1, resultado_cd_4_3=cd_4_3,
    resultado_4_2=r_4_2, resultado_cd_4_2=cd_4_2,
)
injetar_nav("meteorologia.html", "meteorologia")

exportar_barras_dia_semana_4_1(r_4_1, "indicador_4_1_dias_semana.png")
exportar_barras_mes_4_3(r_4_3, "indicador_4_3_por_mes.png")
exportar_barras_dias_alerta_4_2(r_4_2, "indicador_4_2_dias_alerta.png")
exportar_barras_alertas_individuais_4_2(r_4_2, "indicador_4_2_alertas_individuais.png")

print("PASSO 3 concluido: meteorologia.html + 4 PNGs (4.1/4.2/4.3) gerados.\n")


# ============================================================
# PASSO 4 -- salvar tudo na pasta de graficos do Drive
# ============================================================
print("PASSO 4 -- salvando no Drive (pasta de graficos)...")

arquivos_para_salvar = [
    "indicador_2_1_comparacao_64_44.png",
    "indicador_2_2_barras_faixa.png",
    "indicador_4_1_dias_semana.png",
    "indicador_4_2_dias_alerta.png",
    "indicador_4_2_alertas_individuais.png",
    "indicador_4_3_por_mes.png",
    "index.html",
    "meteorologia.html",
]
for nome_arquivo in arquivos_para_salvar:
    drive_io.salvar_arquivo(servico, nome_arquivo, nome_arquivo, config.PASTA_GRAFICOS_ID)

print("\nTudo pronto! Os 8 arquivos foram gerados e salvos na pasta de graficos do Drive.")
print("(Isso NAO publica no site do GitHub Pages")
