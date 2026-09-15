"""
Descrição: teste de persistência (dado "travado") -- compara o
desvio-padrão em janela móvel ao desvio-padrão histórico da própria
estação para cota e vazão.

Conexões do Pipeline:
- Entradas: DataFrame com a coluna gap_temporal (gerada por
  etapa02_step.py), chamado por pipeline_consistencia.py depois de etapa02.
- Saídas: colunas flag_persist_cota, flag_persist_vazao, usadas no resumo
  de flags de pipeline_consistencia.py.

Funções:
- teste_persistencia: calcula o desvio-padrão em janela móvel e compara ao desvio-padrão de referência da estação.
"""
from pathlib import Path

import numpy as np
import pandas as pd


def teste_persistencia(
    df_input,
    janela=8,
    fator_referencia=0.01,
    manter_colunas_auxiliares=False,
    caminho_saida=None
):
    """Classifica cota e vazão como Aprovado/Suspeito/Nulo/'Não testado
    (Gap de dados)', comparando o desvio-padrão em janela móvel (tamanho
    `janela`) ao desvio-padrão histórico da estação multiplicado por
    `fator_referencia`. Janelas que atravessam um gap_temporal não são
    testadas."""
    df = df_input.copy()

    # 1. Validação de Colunas Obrigatórias
    colunas_obrigatorias = ['codigo_estacao', 'data_hora', 'nivel', 'vazao', 'gap_temporal']
    colunas_faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
    if colunas_faltantes:
        raise KeyError(f"Colunas ausentes para o teste: {colunas_faltantes}")

    # Garante que data_hora esteja em formato datetime
    if not pd.api.types.is_datetime64_any_dtype(df['data_hora']):
        df['data_hora'] = pd.to_datetime(df['data_hora'])

    # 2. Ordenação obrigatória por Estação e data_hora
    df = df.sort_values(by=['codigo_estacao', 'data_hora'], ascending=True).reset_index(drop=True)

    # 3. Agrupamento por estação
    grupo = df.groupby('codigo_estacao')

    # 4. Desvio-padrão de referência (Histórico total * fator)
    std_cota_ref = grupo['nivel'].transform('std') * fator_referencia
    std_vazao_ref = grupo['vazao'].transform('std') * fator_referencia

    # 5. Desvio-padrão móvel da janela
    std_movel_cota = grupo['nivel'].transform(lambda x: x.rolling(janela).std())
    std_movel_vazao = grupo['vazao'].transform(lambda x: x.rolling(janela).std())

    # 6. Mapeamento e tratamento das janelas que atravessam um gap temporal
    gap_janela = (
        df['gap_temporal']
        .astype(float)  # True/False -> 1.0/0.0, preserva NaN existentes
        .groupby(df['codigo_estacao'])
        .transform(lambda x: x.rolling(janela).max())
    )

    # 7. Definição dos limiares de comparação
    cota_invalida = std_cota_ref.isna() | std_movel_cota.isna()
    vazao_invalida = std_vazao_ref.isna() | std_movel_vazao.isna()

    # O dado é suspeito se a variação móvel for menor que a referência OU se a referência for zero
    suspeito_cota = (std_movel_cota < std_cota_ref) | (std_cota_ref == 0)
    suspeito_vazao = (std_movel_vazao < std_vazao_ref) | (std_vazao_ref == 0)

    # 8. Regras e Flags para COTA
    # Prioridade: 1º Gap na janela | 2º Nulo/Borda | 3º Teste de Suspeição
    condicoes_cota = [
        gap_janela == 1,
        cota_invalida,
        suspeito_cota,
    ]
    rotulos_cota = ["Não testado (Gap de dados)", "Nulo", "Suspeito"]
    df['flag_persist_cota'] = np.select(condicoes_cota, rotulos_cota, default="Aprovado")

    # 9. Regras e Flags para VAZÃO
    condicoes_vazao = [
        gap_janela == 1,
        vazao_invalida,
        suspeito_vazao,
    ]
    rotulos_vazao = ["Não testado (Gap de dados)", "Nulo", "Suspeito"]
    df['flag_persist_vazao'] = np.select(condicoes_vazao, rotulos_vazao, default="Aprovado")

    # 10. Preservar ou remover colunas auxiliares
    if manter_colunas_auxiliares:
        df['std_cota_ref'] = std_cota_ref
        df['std_vazao_ref'] = std_vazao_ref
        df['std_movel_cota'] = std_movel_cota
        df['std_movel_vazao'] = std_movel_vazao
        df['gap_janela'] = gap_janela

    # 11. Salvamento opcional caso informado um caminho
    if caminho_saida is not None:
        caminho_saida = Path(caminho_saida)
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(caminho_saida)
        print(f"Checkpoint do Persist salvo em: {caminho_saida}")

    return df