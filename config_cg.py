"""
Descrição: parâmetros da visão "Contrato de Gestão" (CG) do dashboard --
períodos, estações excluídas por variável/indicador e nomes das páginas.
Módulo NOVO: não altera config.py, e nada aqui afeta as visões
"Série histórica" (Hidrologia) e "2026" (Meteorologia), que continuam
geradas exatamente como hoje.

Conexões do Pipeline:
- Entradas: nenhuma (apenas constantes).
- Saídas: importado por dashboard_cg.py, meteorologia_cg.py, nav_cg.py e
  teste_colab_f1a.py.

Decisões (Valéria, 26/09/2026):
- Hidrologia CG: 01/07/2026 até a data da rodada do pipeline.
  O 2.1 começa na primeira data disponível na API nova (janela rolante,
  justificativa já aceita) -- o corte de 01/07 é aplicado, mas na
  prática não recorta nada.
- Meteorologia CG: 16/09/2026 até a data da rodada. O CG continua depois
  da virada do ano -> a pasta do SIMGE de cada ano é achada automaticamente
  (ver URLS_SIMGE_POR_ANO; sem desconto de feriados no CG).
- Exclusões (estacoes_excluidas.txt): 2.2 e 2.8 -> NÍVEL sem as 8, CHUVA
  sem as 5; 2.1 -> sem as 5 de chuva.
"""

# ---------------------------------------------------------------------
# Períodos
# ---------------------------------------------------------------------
DATA_INICIO_CG_HIDRO = "2026-07-01"
DATA_INICIO_CG_METEO = "2026-09-16"

# ---------------------------------------------------------------------
# Estações excluídas (desinstaladas/fora de operação) -- estacoes_excluidas.txt
# ---------------------------------------------------------------------
ESTACOES_EXCLUIDAS_NIVEL = frozenset({
    "40100100", "53511000", "54193050", "54195040",
    "54770100", "56988550", "61370000", "61793990",
})
ESTACOES_EXCLUIDAS_CHUVA = frozenset({
    "54193050", "54770100", "56988550", "61370000", "61793990",
})
# 2.1 usa o mesmo filtro da chuva (decisão 26/09)
ESTACOES_EXCLUIDAS_2_1 = ESTACOES_EXCLUIDAS_CHUVA

# As listas acima são só o VALOR PADRÃO. A lista oficial fica num CSV no
# Drive, na MESMA pasta do frente1.csv (config.PASTA_DATA_ID), para poder
# ser editada sem mexer em código:
#     estacoes_excluidas.csv  (separador ";")
#     codigo_estacao;excluir_chuva;excluir_nivel;motivo
#     54193050;sim;sim;desinstalada
#     40100100;nao;sim;fora de operação (nível)
# carregar_exclusoes_do_drive() substitui as listas acima pelas do CSV no
# início de cada rodada. Se o arquivo não existir, valem as listas acima.
NOME_CSV_EXCLUSOES = "estacoes_excluidas.csv"


def carregar_exclusoes_do_drive(servico):
    """Atualiza ESTACOES_EXCLUIDAS_CHUVA / _NIVEL / _2_1 a partir do
    estacoes_excluidas.csv do Drive (config.PASTA_DATA_ID). Devolve True se
    leu o arquivo, False se manteve o padrão deste módulo."""
    global ESTACOES_EXCLUIDAS_CHUVA, ESTACOES_EXCLUIDAS_NIVEL, ESTACOES_EXCLUIDAS_2_1
    import config
    import drive_io
    try:
        df = drive_io.ler_csv(servico, NOME_CSV_EXCLUSOES, config.PASTA_DATA_ID, sep=";")
    except Exception as erro:  # noqa: BLE001
        print(f"  AVISO: erro ao ler {NOME_CSV_EXCLUSOES} ({erro}) -- usando as listas padrão do config_cg.")
        return False
    if df is None or df.empty:
        print(f"  {NOME_CSV_EXCLUSOES} não encontrado no Drive -- usando as listas padrão do config_cg.")
        return False
    df.columns = [c.strip().lstrip("\ufeff").strip().lower() for c in df.columns]
    df["codigo_estacao"] = df["codigo_estacao"].astype(str).str.strip().str.zfill(8)
    sim = lambda col: df[col].astype(str).str.strip().str.lower().isin({"sim", "s", "true", "1", "x"})
    ESTACOES_EXCLUIDAS_CHUVA = frozenset(df.loc[sim("excluir_chuva"), "codigo_estacao"])
    ESTACOES_EXCLUIDAS_NIVEL = frozenset(df.loc[sim("excluir_nivel"), "codigo_estacao"])
    ESTACOES_EXCLUIDAS_2_1 = ESTACOES_EXCLUIDAS_CHUVA
    print(f"  Exclusões lidas de {NOME_CSV_EXCLUSOES}: chuva={len(ESTACOES_EXCLUIDAS_CHUVA)}, "
          f"nível={len(ESTACOES_EXCLUIDAS_NIVEL)}.")
    return True

# ---------------------------------------------------------------------
# Indicador 2.8 -- janela padrão do teste de Persist (em leituras de 15 min)
# ---------------------------------------------------------------------
# 96 leituras = 24 h. É o valor com que foram gerados os gráficos do
# relatório (o etapa03_persist_regional.py da pasta indicador_2_8 está com
# 8, mas a rodada do Colab que gerou o indicador_2_8_bruto.csv usou 96 --
# conferido reproduzindo os status leitura a leitura). Vale até a chefia
# passar as janelas por região (JANELA_POR_REGIAO + coluna 'regiao').
JANELA_PERSIST_PADRAO = 96

# ---------------------------------------------------------------------
# SIMGE -- pastas por ano (Meteorologia CG atravessa a virada do ano)
# ---------------------------------------------------------------------
# Deixe None: a pasta do ano é localizada AUTOMATICAMENTE na página inicial
# do repositório do SIMGE (meteorologia_cg.descobrir_url_pasta_ano). Só
# preencha se um dia a busca automática falhar (a URL preenchida tem
# prioridade). Enquanto o ano não tiver pasta, ele fica fora com AVISO.
from extrair_documentos_simge_ingestao import (  # noqa: E402
    URL_PASTA_PREVISOES_2026,
    URL_PASTA_TENDENCIA_CLIMATICA_2026,
)

URLS_SIMGE_POR_ANO = {
    2026: {"previsoes": URL_PASTA_PREVISOES_2026, "tendencia": URL_PASTA_TENDENCIA_CLIMATICA_2026},
    2027: {"previsoes": None, "tendencia": None},
}

# Feriados: NÃO se aplicam ao Contrato de Gestão (decisão de 27/09 -- os
# meteorologistas trabalham de plantão; 4.1 = 1 previsão por dia corrido).
# O desconto de feriados continua só na visão 2026 (funções originais).

# ---------------------------------------------------------------------
# Gráficos do relatório mensal (gerar_relatorios_visuais.py, 29/09/2026)
# ---------------------------------------------------------------------
# Pasta do Drive onde os PNGs do relatório são SOBRESCRITOS a cada rodada
# (hidro: 2.1/2.2/2.8; meteo: 4.1/4.2/4.3). É a mesma pasta para onde a
# célula de gráficos do Colab (graficos_indicadores.ipynb) enviava os PNGs.
# Para trocar sem mexer no código: variável de ambiente
# PASTA_GRAFICOS_RELATORIO_ID no workflow.
PASTA_GRAFICOS_RELATORIO_ID = "1C6k6gsoKquJ41VfTM-Ae5t8hzBTsxCan"

# ---------------------------------------------------------------------
# Páginas do site
# ---------------------------------------------------------------------
PAGINA_HIDRO_SERIE = "hidrometria.html"
PAGINA_HIDRO_CG = "hidrometria_cg.html"
PAGINA_HIDRO_CONSISTENCIA = "hidrometria_consistencia.html"
PAGINA_METEO_2026 = "meteorologia.html"
PAGINA_METEO_CG = "meteorologia_cg.html"
