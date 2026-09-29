"""
Indicador 2.8 -- Consistencia de Dados: teste de CHUVA.

Cada teste sinaliza seu proprio resultado em coluna propria -- SEM
combinar/priorizar resultados de testes diferentes numa unica
classificacao.

1. Valor impossivel -- coluna UNICA status_chuva (REVISAO 25/09, 2a
   rodada -- MUDANCA DE GRANULARIDADE, nao so de limite):
   - Volta ao limite 1000 (era 4095/4096 na revisao anterior) e a
     categoria "suspeito" SAIU (nao existe mais pra chuva -- so
     aprovado/reprovado/nulo).
   - O teste deixou de avaliar cada LEITURA individualmente e passou a
     avaliar o ACUMULADO MENSAL por estacao: soma-se toda a chuva do mes
     (calendario) e classifica-se esse total.
       soma_mensal entre 0 e 1000mm  -> mes inteiro "aprovado"
       soma_mensal < 0 ou > 1000mm   -> mes inteiro "reprovado"
       mes sem NENHUMA leitura       -> mes inteiro "nulo"
     Toda LEITURA nao-vazia daquele mes herda o veredito do mes (aprovado
     ou reprovado -- nunca "nulo" so por causa do veredito do mes).
   - Uma leitura EM BRANCO (chuva == NaN) continua status_chuva="nulo"
     INDIVIDUALMENTE, independente do veredito do mes -- um mes pode sair
     "aprovado" mesmo tendo uma leitura pontual em branco no meio; essa
     leitura especifica, isolada, ainda aparece como nulo.
   - chuva_mensal_mm (o total do mes usado na classificacao) fica
     exposta na tabela final, para auditoria -- mesmo espirito de
     chuva_diaria_mm (exposta pro teste do CHIRPS).
   - flag_chuva e dado_consistido_chuva continuam REMOVIDOS (revisao
     anterior, redundantes com status_chuva).

2. Comparacao com CHIRPS (Google Earth Engine, projeto
   'priorizacao-estacoes'), coluna divergencia_chuva (True/False -- NaN
   quando falta dado de um dos lados pra comparar): soma diaria da
   estacao > 1,0mm = "choveu"; CHIRPS diario > 1,0mm = "choveu"; divergiu
   se um lado disser que choveu e o outro nao. Tambem exportadas, lado a
   lado, para auditoria: chuva_diaria_mm (total do dia registrado pela
   estacao) e chirps_dia (total do dia segundo o satelite). Este teste
   continua por DIA (nao mudou) e NAO altera status_chuva -- fica
   exposto em suas proprias colunas, sem prioridade sobre o teste de
   valor impossivel.
"""
import numpy as np
import pandas as pd

LIMIAR_CHUVA_MM = 1.0  # so usado na comparacao com o CHIRPS
LIMITE_MIN_APROVADO_CHUVA_MENSAL = 0
LIMITE_MAX_APROVADO_CHUVA_MENSAL = 1000  # REVISAO 25/09 (2a rodada) -- volta a 1000, agora por MES


def agregar_chuva_mensal(df_input):
    """Soma a chuva de cada leitura em total MENSAL (mes calendario), por
    estacao -- base do teste de valor impossivel (REVISAO 25/09: teste
    passa a ser por mes, nao mais por leitura individual). Mes sem
    NENHUMA leitura -> soma NaN (mesma logica que agregar_chuva_diaria ja
    usa por dia, pro CHIRPS)."""
    df = df_input.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["data_hora"]):
        df["data_hora"] = pd.to_datetime(df["data_hora"])
    df["mes"] = df["data_hora"].dt.to_period("M").astype(str)  # "2026-09"

    mensal = (
        df.groupby(["codigo_estacao", "mes"])
        .agg(chuva_mensal_mm=("chuva", "sum"), n_leituras=("chuva", "count"))
        .reset_index()
    )
    mensal.loc[mensal["n_leituras"] == 0, "chuva_mensal_mm"] = np.nan
    return mensal.drop(columns="n_leituras")


def classificar_chuva_mensal(df_mensal):
    """Classifica cada (estacao, mes) a partir de chuva_mensal_mm:
    aprovado (0-1000mm), reprovado (<0 ou >1000mm), nulo (mes sem
    nenhuma leitura -- chuva_mensal_mm NaN)."""
    df = df_mensal.copy()
    condicoes = [
        df["chuva_mensal_mm"].isna(),
        (df["chuva_mensal_mm"] < LIMITE_MIN_APROVADO_CHUVA_MENSAL)
        | (df["chuva_mensal_mm"] > LIMITE_MAX_APROVADO_CHUVA_MENSAL),
    ]
    rotulos = ["nulo", "reprovado"]
    df["status_chuva_mensal"] = np.select(condicoes, rotulos, default="aprovado")
    return df


def teste_valores_impossiveis_chuva(df_input):
    """Classifica status_chuva por LEITURA, mas a decisao aprovado/
    reprovado vem do ACUMULADO DO MES daquela estacao (ver docstring do
    modulo) -- nao mais do valor da propria leitura. Uma leitura em
    branco (chuva NaN) sempre vira 'nulo', mesmo que o mes dela tenha
    saido aprovado ou reprovado."""
    df = df_input.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["data_hora"]):
        df["data_hora"] = pd.to_datetime(df["data_hora"])
    df["mes"] = df["data_hora"].dt.to_period("M").astype(str)

    df_mensal = classificar_chuva_mensal(agregar_chuva_mensal(df))

    df = df.merge(
        df_mensal[["codigo_estacao", "mes", "status_chuva_mensal", "chuva_mensal_mm"]],
        on=["codigo_estacao", "mes"], how="left",
    )
    df["status_chuva"] = np.where(df["chuva"].isna(), "nulo", df["status_chuva_mensal"])
    return df.drop(columns=["status_chuva_mensal"])


def agregar_chuva_diaria(df_input):
    """Soma a chuva de cada leitura em total diario, por estacao -- usado
    SO para a comparacao com o CHIRPS (que e diario por natureza). NAO
    mudou nesta revisao -- so o teste de valor impossivel virou mensal,
    o CHIRPS continua diario."""
    df = df_input.copy()
    if not pd.api.types.is_datetime64_any_dtype(df["data_hora"]):
        df["data_hora"] = pd.to_datetime(df["data_hora"])
    df["data_dia"] = df["data_hora"].dt.normalize()

    diario = (
        df.groupby(["codigo_estacao", "data_dia"])
        .agg(chuva_diaria_mm=("chuva", "sum"), n_leituras=("chuva", "count"))
        .reset_index()
    )
    diario.loc[diario["n_leituras"] == 0, "chuva_diaria_mm"] = np.nan
    return diario.drop(columns="n_leituras")


def extrair_chirps_diario(df_dim_estacao, data_inicio, data_fim, escala_m=5500):
    """Extrai a serie diaria do CHIRPS para cada estacao, no intervalo
    [data_inicio, data_fim). Usa reduceRegions por imagem (um dia de cada
    vez, via .map()) -- e nao getRegion(), que devolve o ID da IMAGEM na
    coluna 'id', nao o codigo_estacao.

    df_dim_estacao precisa ter codigo_estacao, latitude, longitude.
    Requer ee.Authenticate() + ee.Initialize(project='priorizacao-estacoes')
    ja executados na sessao (ver rodar_colab_indicador_2_8.py).
    """
    import ee

    pontos = [
        ee.Feature(
            ee.Geometry.Point([row["longitude"], row["latitude"]]),
            {"codigo_estacao": str(row["codigo_estacao"])},
        )
        for _, row in df_dim_estacao.iterrows()
    ]
    fc = ee.FeatureCollection(pontos)

    colecao = ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate(str(data_inicio), str(data_fim))

    def reduzir_por_dia(imagem):
        data_str = imagem.date().format("YYYY-MM-dd")
        amostras = imagem.reduceRegions(collection=fc, reducer=ee.Reducer.first(), scale=escala_m)
        return amostras.map(lambda f: f.set("data_dia", data_str))

    amostras_todas = colecao.map(reduzir_por_dia).flatten()
    resultado = amostras_todas.getInfo()

    dados = [
        {
            "codigo_estacao": f["properties"].get("codigo_estacao"),
            "data_dia": f["properties"].get("data_dia"),
            "chirps_dia": f["properties"].get("first", np.nan),
        }
        for f in resultado["features"]
    ]
    df = pd.DataFrame(dados)
    df["data_dia"] = pd.to_datetime(df["data_dia"])
    return df


def comparar_com_chirps(df_diario, df_chirps, limiar=LIMIAR_CHUVA_MM):
    """Divergencia diaria: um lado registrou chuva (>limiar) e o outro
    nao. Devolve codigo_estacao/data_dia/chuva_diaria_mm/chirps_dia/
    divergencia_chuva -- um resultado por DIA, que ainda precisa ser
    espalhado para as leituras (ver propagar_comparacao_chirps_para_leituras)."""
    df = df_diario.merge(df_chirps, on=["codigo_estacao", "data_dia"], how="left")
    estacao_choveu = df["chuva_diaria_mm"] > limiar
    chirps_choveu = df["chirps_dia"] > limiar
    tem_ambos = df["chuva_diaria_mm"].notna() & df["chirps_dia"].notna()
    df["divergencia_chuva"] = np.where(tem_ambos, estacao_choveu != chirps_choveu, np.nan)
    return df[["codigo_estacao", "data_dia", "chuva_diaria_mm", "chirps_dia", "divergencia_chuva"]]


def propagar_comparacao_chirps_para_leituras(df_leitura, df_comparacao_diaria):
    """Espalha o resultado da comparacao com CHIRPS (calculado por DIA)
    para cada LEITURA daquele dia -- necessario porque a tabela final e
    por leitura."""
    df = df_leitura.copy()
    if "data_dia" not in df.columns:
        df["data_dia"] = pd.to_datetime(df["data_hora"]).dt.normalize()
    return df.merge(df_comparacao_diaria, on=["codigo_estacao", "data_dia"], how="left")


def montar_tabela_chuva(df_final):
    """codigo_estacao, data (= data_hora, por leitura), dado_bruto_chuva,
    status_chuva (teste de valor impossivel -- REVISAO 25/09: decisao por
    MES, nao mais por leitura; categorias aprovado/reprovado/nulo, sem
    'suspeito'), chuva_mensal_mm (total do mes usado na classificacao,
    exposto pra auditoria) + chuva_12z_mm, chuva_merge_mm, divergencia_merge
    (teste MERGE, por janela 12Z-12Z -- decisao de 28/09/2026, CHIRPS ->
    MERGE, ver decisoes_e_progresso.md) -- cada teste com seu proprio
    resultado, sem combinar nada. flag_chuva e dado_consistido_chuva NAO
    existem mais (eram redundantes com status_chuva).

    ATENCAO: as colunas chirps_dia/divergencia_chuva (CHIRPS) saem daqui
    desde a troca para o MERGE; comparar_com_chirps continua existindo em
    modo reserva/dormant (ver docstring do modulo), mas quem chama este
    montar_tabela_chuva precisa passar df_final ja com as colunas do MERGE
    (captacao_merge.propagar_comparacao_merge_para_leituras)."""
    saida = df_final.rename(columns={"data_hora": "data", "chuva": "dado_bruto_chuva"})
    colunas = [
        "codigo_estacao", "data", "dado_bruto_chuva", "status_chuva", "chuva_mensal_mm",
        "chuva_12z_mm", "chuva_merge_mm", "divergencia_merge",
    ]
    return saida[colunas]
