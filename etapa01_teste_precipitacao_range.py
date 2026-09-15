"""
Descrição: testes de qualidade de precipitação (faixas de intensidade) e
de range estatístico (cota/vazão).

Conexões do Pipeline:
- Entradas: DataFrame de leituras de uma estação (codigo_estacao, chuva,
  nivel, vazao), chamado por pipeline_consistencia.py.
- Saídas: colunas flag_precipitacao, flag_range_cota, flag_range_vazao,
  usadas em sequência por etapa02_step.py e etapa03_persist.py dentro de
  pipeline_consistencia.py.

Funções:
- teste_precipitacao: classifica cada leitura de chuva por faixa de intensidade.
- teste_range: classifica cota e vazão como aprovado/suspeito/reprovado com base no desvio-padrão por estação.
"""

from pathlib import Path

import numpy as np

def teste_precipitacao(df_input, caminho_saida=None):
    """Classifica cada leitura de chuva por faixa de intensidade
    (Nulo, Valor impossível, Sem chuva, Chuva fraca/moderada/forte/violenta),
    gravando o resultado em flag_precipitacao."""
    df = df_input.copy()
    prec = df['chuva']

    condicoes = [
        prec.isna(),
        (prec < 0),
        (prec == 0),
        (prec > 0) & (prec <= 5),
        (prec > 5) & (prec <= 25),
        (prec > 25) & (prec <= 50),
        (prec > 50)
    ]

    rotulos = [
        "Nulo",
        "Valor impossível",
        "Sem chuva",
        "Chuva fraca",
        "Chuva moderada",
        "Chuva forte",
        "Chuva violenta"
    ]

    df['flag_precipitacao'] = np.select(condicoes, rotulos, default="Nulo")

    # Salvamento opcional caso um caminho seja fornecido
    if caminho_saida is not None:
        caminho_saida = Path(caminho_saida)
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)  # Garante que a pasta existe
        df.to_parquet(caminho_saida)
        print(f"Checkpoint intermediário salvo em: {caminho_saida}")

    return df

def teste_range(df_input, k=3, caminho_saida=None):
    """Classifica cota e vazão como Aprovado/Suspeito/Reprovado/Nulo,
    comparando cada leitura ao intervalo [mínimo - k*desvio, máximo +
    k*desvio] histórico da própria estação (flag_range_cota,
    flag_range_vazao)."""
    df = df_input.copy()

    # Validação de colunas
    colunas_obrigatorias = ['codigo_estacao', 'nivel', 'vazao']
    colunas_faltantes = [col for col in colunas_obrigatorias if col not in df_input.columns]

    if colunas_faltantes:
        raise KeyError(f"Colunas ausentes para o teste de Range: {colunas_faltantes}")

    # Agrupamento por codigo_estacao
    grupo_estacao = df.groupby('codigo_estacao')

    # VARIAVEIS COTA
    cota = df['nivel']
    cota_std = grupo_estacao['nivel'].transform('std')
    cota_max = grupo_estacao['nivel'].transform('max')
    cota_min = grupo_estacao['nivel'].transform('min')
    cota_na = cota.isna()

    # VARIAVEIS VAZAO
    vazao = df['vazao']
    vazao_std = grupo_estacao['vazao'].transform('std')
    vazao_max = grupo_estacao['vazao'].transform('max')
    vazao_min = grupo_estacao['vazao'].transform('min')
    vazao_na = vazao.isna()

    # Calculo dos limites inferior e superior de cada grupo:
    limite_inferior_vazao = vazao_min - (k * vazao_std)
    limite_superior_vazao = vazao_max + (k * vazao_std)
    limite_inferior_cota = cota_min - (k * cota_std)
    limite_superior_cota = cota_max + (k * cota_std)

    # Guardar os limites no DF para permitir plotagem e auditoria
    df['limite_inferior_cota'] = limite_inferior_cota
    df['limite_superior_cota'] = limite_superior_cota
    df['limite_inferior_vazao'] = limite_inferior_vazao
    df['limite_superior_vazao'] = limite_superior_vazao

    # Flags Vazão
    condicoes_vazao = [
        vazao_na,  # 1º: Dados nulos
        (vazao < 0),  # 2º: Filtro físico (impossível vazão < 0)
        (vazao < limite_inferior_vazao) | (vazao > limite_superior_vazao),  # 3º: Fora do range estatístico
        (vazao >= limite_inferior_vazao) & (vazao <= limite_superior_vazao)  # 4º: Dentro do range
    ]

    rotulos_vazao = ["Nulo", "Reprovado", "Suspeito", "Aprovado"]

    df['flag_range_vazao'] = np.select(condicoes_vazao, rotulos_vazao, default="Reprovado")

    # Flags Cota -- não filtra valores negativos, pois podem existir valores abaixo da régua
    condicoes_cota = [
        cota_na,
        (cota < limite_inferior_cota) | (cota > limite_superior_cota),
        (cota >= limite_inferior_cota) & (cota <= limite_superior_cota)
    ]

    rotulos_cota = ["Nulo", "Suspeito", "Aprovado"]

    df['flag_range_cota'] = np.select(condicoes_cota, rotulos_cota, default="Reprovado")

    # Salvamento opcional caso um caminho seja fornecido
    if caminho_saida is not None:
        caminho_saida = Path(caminho_saida)
        caminho_saida.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(caminho_saida)
        print(f"Checkpoint intermediário salvo em: {caminho_saida}")

    return df

