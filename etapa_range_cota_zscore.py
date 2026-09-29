"""
Indicador 2.8 -- Consistencia de Dados: deteccao de GAP + teste de RANGE
para NIVEL, por LEITURA.

Sinaliza seu proprio resultado em coluna propria -- sem combinar com o
resultado do Persist (ver etapa03_persist_regional.py). A unica relacao
entre os dois testes e a regra de dependencia do Persist (roda so quando
status_nivel_range == "aprovado") -- isso e uma regra de EXECUCAO, nao
uma fusao de resultados. Essa regra continua funcionando sem alteracao
com a metodologia nova abaixo, porque ela testa "!= aprovado" (nao uma
lista fixa de valores) -- "suspeito" ja cai automaticamente como "Persist
nao roda", que era o mesmo comportamento de "reprovado" antes.

Gap (coluna gap_temporal): gap_temporal = True quando o nivel esta vazio
naquela leitura (as leituras chegam sempre no grid fixo de 15 min -- o
que pode faltar e o VALOR na coluna nivel, nao a leitura em si).

Range -- METODOLOGIA REVISADA (25/09), com 3 faixas (Aprovado/Suspeito/
Reprovado) usando DOIS metodos combinados, conforme especificacao:
  - Minimo/Maximo APROVADO: vem de valores_min_max.csv (colunas
    cod_estacao, minimo, maximo), UM POR ESTACAO -- valor exato definido
    externamente (nao calculado), diferente do resto do pipeline.
  - Minimo/Maximo SUSPEITO: estimado por z-score, fechado em `ic` (padrao
    IC 95%, decisao da equipe): minimo_suspeito = media - z_critico*desvio,
    maximo_suspeito = media + z_critico*desvio (media/desvio da serie
    historica da propria estacao).
Classificacao por leitura:
    sem dado                                                    -> "nulo"
    minimo_aprovado <= nivel <= maximo_aprovado                  -> "aprovado"
    (minimo_suspeito <= nivel < minimo_aprovado) OU
    (maximo_aprovado < nivel <= maximo_suspeito)                 -> "suspeito"
    nivel < minimo_suspeito OU nivel > maximo_suspeito           -> "reprovado"

Isso SUBSTITUI o metodo anterior (nivel<0 fixo + |z|>z_critico -- sem
banda de "suspeito" propria). O hardcoded "nivel<0 -> reprovado" saiu:
agora quem define o piso "aprovado" e o valor por estacao do CSV, que
pode ser diferente de zero.

Estacao SEM linha em valores_min_max.csv (minimo/maximo ausentes depois
do merge): ASSUNCAO -- cai de volta no comportamento antigo (so
z-score: minimo_aprovado = minimo_suspeito e maximo_aprovado =
maximo_suspeito, ou seja, sem banda de "suspeito" por min/max pra essa
estacao -- so aprovado/reprovado por z-score puro). Um aviso e impresso
listando essas estacoes. CONFIRME se esse fallback e o que voce quer.

z_score_cota, z_critico, minimo_aprovado, maximo_aprovado,
minimo_suspeito, maximo_suspeito continuam expostas (uteis pra
auditoria) -- so flag_range_cota e dado_consistido_nivel_range
continuam fora (redundantes com status_nivel_range, revisao anterior).
"""
import numpy as np
import pandas as pd
from scipy import stats


def calcular_gap_leitura(df_input):
    """Sinaliza (gap_temporal) quando o VALOR de nivel esta ausente
    naquela leitura especifica."""
    df = df_input.copy()
    df["gap_temporal"] = df["nivel"].isna()
    return df


def teste_range_zscore(df_input, df_min_max, ic=0.95):
    """Classifica status_nivel_range ('aprovado' / 'suspeito' /
    'reprovado' / 'nulo') usando minimo/maximo aprovado por estacao (de
    `df_min_max`) e minimo/maximo suspeito por z-score (fechado em `ic`,
    padrao 0.95). Ver docstring do modulo para a regra completa e o
    fallback de estacao sem min/max informado.

    Parametros
    ----------
    df_min_max : pd.DataFrame
        Colunas cod_estacao, minimo, maximo -- um valor por estacao (o
        arquivo valores_min_max.csv, ja carregado pelo chamador)."""
    df = df_input.copy()

    colunas_obrigatorias = ["codigo_estacao", "nivel"]
    faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
    if faltantes:
        raise KeyError(f"Colunas ausentes para o teste de Range: {faltantes}")

    colunas_min_max = ["cod_estacao", "minimo", "maximo"]
    faltantes_min_max = [c for c in colunas_min_max if c not in df_min_max.columns]
    if faltantes_min_max:
        raise KeyError(f"Colunas ausentes em valores_min_max.csv: {faltantes_min_max}")

    limites = df_min_max.copy()
    limites["codigo_estacao"] = limites["cod_estacao"].astype(str).str.zfill(8)
    limites = limites.set_index("codigo_estacao")[["minimo", "maximo"]]

    df["minimo_aprovado"] = df["codigo_estacao"].map(limites["minimo"])
    df["maximo_aprovado"] = df["codigo_estacao"].map(limites["maximo"])

    codigos_sem_limite = sorted(
        df.loc[df["minimo_aprovado"].isna() | df["maximo_aprovado"].isna(), "codigo_estacao"].unique()
    )
    if codigos_sem_limite:
        print(
            f"AVISO: {len(codigos_sem_limite)} estação(ões) sem minimo/maximo em "
            f"valores_min_max.csv -- vão usar só o z-score (sem banda de 'suspeito' "
            f"por min/max, ver docstring do módulo): {codigos_sem_limite}"
        )

    grupo = df.groupby("codigo_estacao")["nivel"]
    media = grupo.transform("mean")
    desvio = grupo.transform("std")
    z = (df["nivel"] - media) / desvio
    df["z_score_cota"] = z

    z_critico = stats.norm.ppf(0.5 + ic / 2)
    df["z_critico"] = z_critico
    df["minimo_suspeito"] = media - z_critico * desvio
    df["maximo_suspeito"] = media + z_critico * desvio

    # Fallback (estacao sem min/max no CSV): banda de aprovado colapsa na
    # banda de suspeito -- ver ASSUNCAO na docstring do modulo.
    minimo_aprovado_efetivo = df["minimo_aprovado"].fillna(df["minimo_suspeito"])
    maximo_aprovado_efetivo = df["maximo_aprovado"].fillna(df["maximo_suspeito"])

    condicoes = [
        df["nivel"].isna() | df["minimo_suspeito"].isna() | df["maximo_suspeito"].isna(),
        (df["nivel"] < df["minimo_suspeito"]) | (df["nivel"] > df["maximo_suspeito"]),
        (df["nivel"] < minimo_aprovado_efetivo) | (df["nivel"] > maximo_aprovado_efetivo),
    ]
    rotulos = ["nulo", "reprovado", "suspeito"]
    df["status_nivel_range"] = np.select(condicoes, rotulos, default="aprovado")

    return df
