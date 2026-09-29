"""
Descrição: fato detalhado de consistência do indicador 2.8, POR LEITURA,
com chuva e nível lado a lado -- criado em 29/09/2026 a pedido da equipe,
para alimentar a nova aba "Consistência por Estação" do dashboard (painel
interativo, ver decisoes_e_progresso.md) e uma planilha para um colega.

NÃO substitui nem altera o cálculo oficial do 2.8 (nota, gráficos de
qualidade) -- é um export ADICIONAL, só de leitura, montado a partir dos
mesmos dados e das mesmas funções que o pipeline já usa
(etapa_range_cota_zscore, etapa03_persist_regional, etapa01_teste_chuva,
captacao_merge). Onde o pipeline oficial (indicador_2_8_calculo.testar_nivel)
já descarta as colunas de diagnóstico do Range (minimo_aprovado,
z_score_cota etc. -- redundantes para a nota), este módulo as recalcula e
mantém, porque são exatamente o que se precisa para auditar/plotar por
estação. Isso recalcula Range e Persist uma segunda vez (o cálculo é
barato: operações vetorizadas por estação); nenhum resultado usado na nota
oficial vem daqui.

ATENÇÃO -- nomes de coluna: este módulo usa os nomes ATUAIS do pipeline
(chuva_12z_mm, chuva_merge_mm, divergencia_merge -- decisão de 28/09/2026,
CHIRPS -> MERGE). Um export manual anterior (26/09) ainda tinha
chirps_dia/divergencia_chuva; quem for adaptar uma planilha ou script feito
com base naquele export precisa trocar esses nomes.

ATENÇÃO -- decimal/separador: salvo com drive_io.salvar_csv, ou seja,
separador VÍRGULA e decimal PONTO, codificação utf-8-sig (o mesmo padrão
de todo o resto do pipeline). Abrir este arquivo com duplo clique no Excel,
em máquina configurada em português, pode fazer o Excel reinterpretar os
números sozinho -- foi exatamente isso (aparentemente) que corrompeu o
z_critico (virou "1,95996E+15") e uma trave de chuva em ~30 das 55 estações
do painel atual (valores da ordem de 1e15-1e17 mm, encontrados numa
conferência em 29/09/2026). Para abrir sem risco: usar "Dados > Obter
Dados > De Texto/CSV" no Excel e conferir o separador/decimal na tela de
importação, em vez de abrir direto.

Conexões do Pipeline:
- Entradas: as mesmas de indicador_2_8_calculo.testar_nivel/testar_chuva/
  aplicar_merge (df_periodo por estação, df_min_max, df_regiao, dim,
  servico) -- chamado DEPOIS desses, reaproveitando o que já foi lido do
  Drive (não lê nada a mais do Drive além do que o pipeline já leria).
- Saídas: um único CSV, uma linha por (codigo_estacao, data_hora), com
  todas as colunas de chuva e de nível juntas -- pensado para virar a
  planilha/base do painel "Consistência por Estação".
"""
import numpy as np
import pandas as pd

import etapa01_teste_chuva as chuva
import etapa03_persist_regional as persist
import etapa_range_cota_zscore as range_cota

NOME_ARQUIVO_FATO = "fato_consistencia_estacao.csv"

# Colunas de nível preservadas (a diferença para etapa03_persist_regional.montar_tabela_cota
# é que aqui NADA é descartado -- inclusive as colunas de diagnóstico do Range).
COLUNAS_NIVEL_DETALHADO = [
    "codigo_estacao", "data_hora", "nivel", "gap_temporal",
    "minimo_aprovado", "maximo_aprovado", "z_score_cota", "z_critico",
    "minimo_suspeito", "maximo_suspeito", "status_nivel_range",
    "status_nivel_persist", "janela_persist_usada",
]
COLUNAS_CHUVA_DETALHADO = [
    "codigo_estacao", "data_hora", "chuva", "status_chuva", "chuva_mensal_mm",
    "chuva_12z_mm", "chuva_merge_mm", "divergencia_merge",
]


def montar_fato_nivel(df_periodo, df_min_max, df_regiao):
    """Range + Persist por leitura, SEM descartar as colunas de diagnóstico
    (diferente de indicador_2_8_calculo.testar_nivel, que já devolve a
    versão enxuta via montar_tabela_cota). Mesmas três chamadas, mesmos
    parâmetros -- só a seleção final de colunas muda."""
    df_gap = range_cota.calcular_gap_leitura(df_periodo)
    df_range = range_cota.teste_range_zscore(df_gap, df_min_max)
    df_persist = persist.teste_persistencia_regional(df_range, df_regiao_estacao=df_regiao)
    colunas = [c for c in COLUNAS_NIVEL_DETALHADO if c in df_persist.columns]
    return df_persist[colunas]


def montar_fato_chuva(df_periodo, fato_merge):
    """status_chuva (mensal) + a comparação com o MERGE, por leitura, sem
    passar pela seleção enxuta de etapa01_teste_chuva.montar_tabela_chuva
    (que também teria servido -- aqui só para deixar explícito que este
    módulo nunca depende do trimming da tabela oficial, e para manter a
    coluna 'chuva' com esse nome, igual ao lado do nível).

    fato_merge: saída de captacao_merge.comparar_com_merge para ESTA
    estação (codigo_estacao, data_dia, chuva_12z_mm, chuva_merge_mm,
    divergencia_merge) -- passe um recorte vazio (mesmas colunas, 0 linhas)
    se o MERGE não estiver disponível nesta rodada."""
    df_status = chuva.teste_valores_impossiveis_chuva(df_periodo)
    df = captacao_merge_propagar(df_status, fato_merge)
    colunas = [c for c in COLUNAS_CHUVA_DETALHADO if c in df.columns]
    return df[colunas]


def captacao_merge_propagar(df_status, fato_merge):
    """Import tardio para não criar um ciclo de import no módulo
    captacao_merge (que não precisa conhecer este módulo)."""
    import captacao_merge
    return captacao_merge.propagar_comparacao_merge_para_leituras(df_status, fato_merge)


def montar_fato_estacao(df_periodo, df_min_max, df_regiao, fato_merge, entra_chuva, entra_nivel):
    """Uma estação: chuva e nível lado a lado (outer join por
    codigo_estacao + data_hora), só com os lados que essa estação tem
    (entra_chuva/entra_nivel, de indicador_2_8_calculo.universo_da_estacao).
    Devolve None se a estação não entra em nenhum dos dois."""
    partes = []
    if entra_chuva:
        partes.append(("chuva", montar_fato_chuva(df_periodo, fato_merge)))
    if entra_nivel:
        partes.append(("nivel", montar_fato_nivel(df_periodo, df_min_max, df_regiao)))
    if not partes:
        return None
    if len(partes) == 1:
        return partes[0][1]
    _, fato = partes[0]
    for _, outro in partes[1:]:
        fato = fato.merge(outro, on=["codigo_estacao", "data_hora"], how="outer")
    return fato


def montar_fato_completo(fatos_por_estacao):
    """Concatena o fato de todas as estações (lista de DataFrames, uma por
    estação, já sem as None) e ordena por estação e horário -- pronta para
    salvar como CSV/planilha."""
    if not fatos_por_estacao:
        return pd.DataFrame()
    fato = pd.concat(fatos_por_estacao, ignore_index=True)
    return fato.sort_values(["codigo_estacao", "data_hora"]).reset_index(drop=True)
