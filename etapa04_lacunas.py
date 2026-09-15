"""
Descrição: calcula o percentual diário de disponibilidade de dados
(chuva/cota/vazão) por estação, comparando registros válidos com registros
esperados.

Conexões do Pipeline:
- Entradas: DataFrame de leituras de uma estação (codigo_estacao,
  data_hora, chuva, nivel, vazao), chamado por pipeline_consistencia.py.
- Saídas: alimenta fato_disponibilidade.csv (via pipeline_consistencia.py)
  e, por consequência, indicador_2_2_calculo.py.

Funções:
- calcular_disponibilidade:
    Calcula, por estação e por dia, o percentual de disponibilidade dos
    dados (registros válidos / registros esperados) para Chuva, Cota e
    Vazão. Alimenta o indicador 2.2 (% de transmissão sem perda de
    registros).

    Para todos os dias completos, o esperado é `total_leituras` (default 96,
    equivalente a uma leitura a cada 15 min ao longo de 24h). Para o dia mais
    recente de cada estação -- que normalmente está incompleto, porque a
    coleta ainda não "fechou" as 24h no momento em que os dados foram
    puxados -- o esperado é ajustado proporcionalmente: se a última leitura
    daquele dia foi às 06:00, por exemplo, só se espera as leituras possíveis
    entre 00:00 e 06:00, não as 96 do dia inteiro.
"""
from pathlib import Path

import numpy as np
import pandas as pd


def calcular_disponibilidade(
    df_input,
    manter_colunas_auxiliares=False,
    caminho_saida=None,
    total_leituras=96,
    intervalo_minutos=15,
    data_fim_grade=None,
):
    """
    Parâmetros:
    df_input : pd.DataFrame
        Precisa conter 'codigo_estacao', 'data_hora', 'chuva', 'nivel' e
        'vazao' (mesmo que alguma delas seja inteiramente vazia para essa
        estação).
    manter_colunas_auxiliares : bool
        Se True, preserva as contagens brutas e o número de leituras
        esperadas usado em cada dia.
    caminho_saida : Path ou str, opcional
        Caminho para salvar o checkpoint em Parquet.
    total_leituras : int
        Nº de leituras esperadas num dia completo (default 96 = intervalo de 15 min).
    intervalo_minutos : int
        Intervalo entre leituras, em minutos (default 15 = total_leituras=96).
    data_fim_grade : data, opcional (ajuste 10/09)
        Data final da grade de dias -- a MESMA data pra todas as estações,
        normalmente a data de execução do pipeline. Se None, usa a data de
        hoje no momento do cálculo (uso standalone/teste).

        Antes desse ajuste, a grade de cada estação terminava em
        `grupo["data_dia"].max()` (o último dia em que ELA teve dado) --
        então uma estação que parasse de transmitir simplesmente "sumia" do
        relatório de disponibilidade a partir do dia da última leitura, em
        vez de continuar contando dias de lacuna (0%) enquanto seguisse
        silenciosa. Com `data_fim_grade`, a grade vai até a rodada atual pra
        todas, e os dias sem leitura entre a última transmissão e hoje
        entram como lacuna normalmente. O tratamento do dia mais recente
        COM dado (leituras esperadas ajustadas proporcionalmente ao horário
        da última leitura -- ver docstring do módulo) não muda: ele continua
        valendo só pro dia real da última leitura de cada estação, nunca
        pros dias de padding adicionados por este ajuste.
    """
    df = df_input.copy()

    # 1. Validação de colunas obrigatórias.
    colunas_obrigatorias = ["codigo_estacao", "data_hora", "chuva", "nivel", "vazao"]

    colunas_faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
    if colunas_faltantes:
        raise KeyError(f"Colunas ausentes para o cálculo de Disponibilidade: {colunas_faltantes}")

    if not pd.api.types.is_datetime64_any_dtype(df["data_hora"]):
        df["data_hora"] = pd.to_datetime(df["data_hora"])

    # 2. Ordenação
    df = df.sort_values(by=["codigo_estacao", "data_hora"]).reset_index(drop=True)

    # 3. Extrai o dia (sem hora) para poder agrupar por dia.
    df["data_dia"] = df["data_hora"].dt.normalize()

    # 4. Conta quantos registros válidos (não-NaN) cada estação teve, por dia,
    #    separadamente para Chuva, Cota e Vazão.
    df_diario_chuva = (
        df.groupby(["codigo_estacao", "data_dia"])["chuva"]
        .count()
        .reset_index(name="registros_validos_chuva")
    )
    df_diario_cota = (
        df.groupby(["codigo_estacao", "data_dia"])["nivel"]
        .count()
        .reset_index(name="registros_validos_cota")
    )
    df_diario_vazao = (
        df.groupby(["codigo_estacao", "data_dia"])["vazao"]
        .count()
        .reset_index(name="registros_validos_vazao")
    )

    # 5. Última leitura de cada estação -- define até onde o dia mais recente
    #    foi realmente coberto.
    ultima_leitura_estacao = df.groupby("codigo_estacao")["data_hora"].max()

    # 6. Grade de dias completa -- POR ESTAÇÃO, do primeiro dia com dado dela
    #    (nunca dias anteriores à sua instalação) até `data_fim_grade` -- a
    #    MESMA data final pra todas as estações (ajuste 10/09, ver docstring
    #    de data_fim_grade acima), não mais o último dia com dado de cada
    #    uma. O max() com o último dia real da estação é só uma salvaguarda
    #    pra nunca cortar dado de verdade, caso data_fim_grade venha anterior
    #    à última leitura por algum motivo.
    #
    #    data_fim_grade pode chegar tz-aware (ex.: data_execucao com fuso
    #    America/Sao_Paulo, vindo de pipeline_consistencia.py) enquanto
    #    "data_dia" aqui é sempre tz-naive (df["data_hora"] vem do Drive sem
    #    fuso) -- comparar/misturar os dois direto quebra com "Cannot compare
    #    tz-naive and tz-aware timestamps". Por isso removemos o fuso antes
    #    de qualquer comparação, sem alterar o horário local.
    fim_grade = pd.Timestamp(data_fim_grade) if data_fim_grade is not None else pd.Timestamp.now()
    if fim_grade.tzinfo is not None:
        fim_grade = fim_grade.tz_localize(None)
    fim_grade = fim_grade.normalize()
    grades = []
    for estacao, grupo in df.groupby("codigo_estacao"):
        fim_estacao = max(fim_grade, grupo["data_dia"].max())
        dias_estacao = pd.date_range(
            start=grupo["data_dia"].min(), end=fim_estacao, freq="D"
        )
        grades.append(pd.DataFrame({"codigo_estacao": estacao, "data_dia": dias_estacao}))
    grade_completa = pd.concat(grades, ignore_index=True)

    df_diario = grade_completa.merge(
        df_diario_chuva, on=["codigo_estacao", "data_dia"], how="left"
    )
    df_diario = df_diario.merge(
        df_diario_cota, on=["codigo_estacao", "data_dia"], how="left"
    )
    df_diario = df_diario.merge(
        df_diario_vazao, on=["codigo_estacao", "data_dia"], how="left"
    )

    df_diario["registros_validos_chuva"] = df_diario["registros_validos_chuva"].fillna(0).astype(int)
    df_diario["registros_validos_cota"] = df_diario["registros_validos_cota"].fillna(0).astype(int)
    df_diario["registros_validos_vazao"] = df_diario["registros_validos_vazao"].fillna(0).astype(int)

    # 7. Leituras esperadas por dia: total_leituras para dias completos;
    #    ajustado ao horário da última leitura, só para o último dia de cada
    #    estação (que normalmente está incompleto).
    ultima_leitura_mapeada = df_diario["codigo_estacao"].map(ultima_leitura_estacao)
    e_ultimo_dia = df_diario["data_dia"] == ultima_leitura_mapeada.dt.normalize()

    minutos_desde_meia_noite = (
        (ultima_leitura_mapeada - df_diario["data_dia"]).dt.total_seconds() / 60
    )
    leituras_esperadas_ultimo_dia = (
        (minutos_desde_meia_noite // intervalo_minutos) + 1
    ).clip(lower=1, upper=total_leituras)

    df_diario["leituras_esperadas"] = np.where(
        e_ultimo_dia, leituras_esperadas_ultimo_dia, total_leituras
    )

    # 8. Indicador: razão entre disponível e esperado, em %.
    df_diario["disponibilidade_chuva_percentual"] = (
        (df_diario["registros_validos_chuva"] / df_diario["leituras_esperadas"]) * 100
    ).round(2).clip(upper=100)
    df_diario["disponibilidade_cota_percentual"] = (
        (df_diario["registros_validos_cota"] / df_diario["leituras_esperadas"]) * 100
    ).round(2).clip(upper=100)
    df_diario["disponibilidade_vazao_percentual"] = (
        (df_diario["registros_validos_vazao"] / df_diario["leituras_esperadas"]) * 100
    ).round(2).clip(upper=100)

    # 9. Colunas auxiliares (contagem bruta e leituras esperadas).
    if not manter_colunas_auxiliares:
        df_diario = df_diario.drop(
            columns=[
                "registros_validos_chuva", "registros_validos_cota",
                "registros_validos_vazao", "leituras_esperadas",
            ]
        )

    # 10. Salvamento opcional.
    if caminho_saida is not None:
        caminho_saida = Path(caminho_saida)
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        df_diario.to_parquet(caminho_saida)
        print(f"Checkpoint do cálculo de Disponibilidade salvo em: {caminho_saida}")

    return df_diario
