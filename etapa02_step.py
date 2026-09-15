"""
Descrição: aplica o teste de taxa de variação (Step) para cota e
vazão, sinalizando quedas/subidas fora do esperado e gaps temporais.

Conexões do Pipeline:
- Entradas: DataFrame de leituras de uma estação (codigo_estacao,
  data_hora, nivel, vazao), chamado por pipeline_consistencia.py.
- Saídas: coluna 'gap_temporal' consumida pelo teste de
  Persistência (etapa03_persist.py).

Funções:
- teste_step: aplica o teste de Step e devolve o DataFrame com as flags de variação.
"""
from pathlib import Path
import numpy as np
import pandas as pd


def teste_step(
    df_input,
    limite_tempo_semdados_hora=1.0,
    quantile_subida=0.995,
    quantile_descida=0.005,
    manter_colunas_auxiliares=False,
    caminho_saida=None
):
    """
    Aplica o teste de taxa de variação (Step/Degrau) para cota e vazão.

    Parâmetros:
    -----------
    df_input : pd.DataFrame
        DataFrame contendo 'codigo_estacao', 'data_hora', 'nivel' e 'vazao'.
    limite_tempo_semdados_hora : float
        Intervalo máximo de tempo (em horas) para considerar a taxa válida. Acima disso é considerado Gap.
    quantile_subida : float
        Percentil para limite máximo de subida estatística (ex: 0.995 para P99.5).
    quantile_descida : float
        Percentil para limite máximo de descida estatística (ex: 0.005 para P0.5).
    manter_colunas_auxiliares : bool
        Se True, preserva as colunas de taxas e limites calculados no DataFrame final
        (gap_temporal e as flags sempre aparecem, independente desta opção).
    caminho_saida : Path ou str, opcional
        Caminho para salvar o checkpoint intermediário em Parquet.
    """
    df = df_input.copy()

    # 1. Validação de Colunas Obrigatórias
    colunas_obrigatorias = ['codigo_estacao', 'data_hora', 'nivel', 'vazao']
    colunas_faltantes = [col for col in colunas_obrigatorias if col not in df.columns]
    if colunas_faltantes:
        raise KeyError(f"Colunas ausentes para o teste de Step: {colunas_faltantes}")

    # Garante que data_hora esteja em formato datetime
    if not pd.api.types.is_datetime64_any_dtype(df['data_hora']):
        df['data_hora'] = pd.to_datetime(df['data_hora'])

    # 2. Ordenação obrigatória por Estação e data_hora
    df = df.sort_values(by=['codigo_estacao', 'data_hora'], ascending=True).reset_index(drop=True)

    # 3. Agrupamento por estação
    grupo = df.groupby('codigo_estacao')

    # 4. Variações absolutas e de tempo
    variacao_cota = grupo['nivel'].diff()
    variacao_vazao = grupo['vazao'].diff()
    variacao_tempo = grupo['data_hora'].diff()

    # Converter tempo para horas decimais
    variacao_tempo_hora = variacao_tempo.dt.total_seconds() / 3600.0

    # Evitar divisão por zero substituindo 0 por NaN
    horas_validas = variacao_tempo_hora.replace(0, np.nan)

    # Taxas de variação por hora (cm/h e m³/s por hora)
    taxa_var_cota = variacao_cota / horas_validas
    taxa_var_vazao = variacao_vazao / horas_validas

    # Identificação de gap temporal (intervalo maior que o esperado desde a leitura anterior)
    gap_temporal = variacao_tempo_hora > limite_tempo_semdados_hora

    # 5. Cálculo dos Limites Estatísticos via Transform

    # Cota - Subida
    taxa_cota_subida = taxa_var_cota.where((taxa_var_cota > 0) & ~gap_temporal)
    quantis_subida_cota = taxa_cota_subida.groupby(df['codigo_estacao']).quantile(quantile_subida)
    limite_subida_cota = df['codigo_estacao'].map(quantis_subida_cota)

    # Cota - Descida
    taxa_cota_descida = taxa_var_cota.where((taxa_var_cota < 0) & ~gap_temporal)
    quantis_descida_cota = taxa_cota_descida.groupby(df['codigo_estacao']).quantile(quantile_descida)
    limite_descida_cota = df['codigo_estacao'].map(quantis_descida_cota)

    # Vazão - Subida
    taxa_vazao_subida = taxa_var_vazao.where((taxa_var_vazao > 0) & ~gap_temporal)
    quantis_subida_vazao = taxa_vazao_subida.groupby(df['codigo_estacao']).quantile(quantile_subida)
    limite_subida_vazao = df['codigo_estacao'].map(quantis_subida_vazao)

    # Vazão - Descida
    taxa_vazao_descida = taxa_var_vazao.where((taxa_var_vazao < 0) & ~gap_temporal)
    quantis_descida_vazao = taxa_vazao_descida.groupby(df['codigo_estacao']).quantile(quantile_descida)
    limite_descida_vazao = df['codigo_estacao'].map(quantis_descida_vazao)

    # 6. Atribuição das Flags de Cota
    cota_na = df['nivel'].isna() | taxa_var_cota.isna()

    condicoes_cota = [
        cota_na,
        gap_temporal,
        taxa_var_cota > limite_subida_cota,
        taxa_var_cota < limite_descida_cota
    ]
    rotulos_cota = ["Nulo", "Não testado (Gap de dados)", "Subida suspeita", "Descida suspeita"]
    df['flag_step_cota'] = np.select(condicoes_cota, rotulos_cota, default="Aprovado")

    # 7. Atribuição das Flags de Vazão
    vazao_na = df['vazao'].isna() | taxa_var_vazao.isna()

    condicoes_vazao = [
        vazao_na,
        gap_temporal,
        taxa_var_vazao > limite_subida_vazao,
        taxa_var_vazao < limite_descida_vazao
    ]
    rotulos_vazao = ["Nulo", "Não testado (Gap de dados)", "Subida suspeita", "Descida suspeita"]
    df['flag_step_vazao'] = np.select(condicoes_vazao, rotulos_vazao, default="Aprovado")

    # gap_temporal sempre presente -- o teste de Persistencia depende dela
    df['gap_temporal'] = gap_temporal

    # 8. Preservar ou remover colunas auxiliares (taxas/limites de calculo)
    if manter_colunas_auxiliares:
        df['variacao_tempo_hora'] = variacao_tempo_hora
        df['taxa_var_cota'] = taxa_var_cota
        df['taxa_var_vazao'] = taxa_var_vazao
        df['limite_subida_cota'] = limite_subida_cota
        df['limite_descida_cota'] = limite_descida_cota
        df['limite_subida_vazao'] = limite_subida_vazao
        df['limite_descida_vazao'] = limite_descida_vazao

    # 9. Salvamento opcional caso informado um caminho
    if caminho_saida is not None:
        caminho_saida = Path(caminho_saida)
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(caminho_saida)
        print(f"Checkpoint do Step salvo em: {caminho_saida}")

    return df