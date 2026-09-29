"""
Indicador 2.8 -- Consistencia de Dados: teste de PERSIST (nivel), por
LEITURA, com janela regional e dependencia do teste de Range.

Sinaliza seu proprio resultado na coluna UNICA status_nivel_persist
(REVISAO 24/09: flag_persist_cota e dado_consistido_nivel_persist foram
REMOVIDOS por serem redundantes) -- sem combinar com o resultado do
Range (ver etapa_range_cota_zscore.py). status_nivel_persist tem 4
valores (diferente de chuva e range, que tem 3 -- decisao explicita do
usuario em 24/09, para nao forcar o Persist a caber em 3 categorias):
    "aprovado"              -> passou no teste de Persist
    "reprovado"             -> Suspeito (variancia da janela movel abaixo
                                 do minimo esperado)
    "nulo"                  -> nivel vazio nessa leitura, status_nivel_range
                                 == "nulo", OU a serie INTEIRA da estacao nao
                                 tem desvio-padrao (menos de 2 leituras de
                                 nivel validas no periodo inteiro -- estacao
                                 sem base nenhuma pra testar, nao e temporario)
    "Teste não realizado"   -> status_nivel_range == "reprovado" (Range nao
                                 aprovou); OU a janela movel tinha gap de
                                 dados; OU esta leitura ainda nao tem as
                                 `janela` leituras anteriores acumuladas
                                 (comeco da serie de cada estacao -- nivel
                                 PRESENTE, so falta historico; correcao de
                                 29/09/2026: antes caia em "nulo" por engano,
                                 dando a entender que faltava dado quando na
                                 verdade so faltava tempo de janela).

Regra de dependencia (confirmada, nao mais em aberto): o Persist SO roda
quando status_nivel_range == "aprovado". Qualquer outro resultado do
Range ("reprovado") -> status_nivel_persist = "Teste não realizado". Se
o proprio Range ja for "nulo" (sem dado), o Persist tambem fica "nulo".
Essa e uma regra de EXECUCAO (decide se o teste roda), nao uma fusao de
resultados -- os dois testes continuam saindo em colunas separadas.
"""
import numpy as np
import pandas as pd

JANELA_POR_REGIAO = {
    # "regiao": tamanho_da_janela_em_LEITURAS -- AGUARDANDO valores da Valeria.
}
# Valor de PRODUÇÃO: 96 leituras = 24h (decisão de 27/09/2026). Fica aqui, não só em
# config_cg.JANELA_PERSIST_PADRAO, para que qualquer uso deste módulo -- inclusive um
# teste no Colab que não passe por indicador_2_8_calculo.py -- já rode com a janela
# certa por padrão, em vez de cair silenciosamente numa janela de teste (era 8 antes
# desta correção, 29/09/2026). indicador_2_8_calculo.py ainda sobrescreve este valor a
# partir de config_cg.JANELA_PERSIST_PADRAO, que continua sendo o lugar certo para
# mudar o valor de produção -- os dois devem ficar iguais.
JANELA_PADRAO_FALLBACK = 96


def teste_persistencia_regional(df_input, coluna_status_range="status_nivel_range", df_regiao_estacao=None, fator_referencia=0.01):
    """
    Parametros
    ----------
    coluna_status_range : str
        Nome da coluna de Range usada SO na regra de dependencia (decide
        se o Persist roda ou nao) -- nao entra na classificacao do
        Persist em si. Espera os valores 'aprovado' / 'reprovado' /
        'nulo' (saida de etapa_range_cota_zscore.teste_range_zscore).
    df_regiao_estacao : pd.DataFrame, opcional
        Colunas codigo_estacao, regiao. Se None, toda estacao usa
        JANELA_PADRAO_FALLBACK.
    """
    df = df_input.copy()

    colunas_obrigatorias = ["codigo_estacao", "data_hora", "nivel", "gap_temporal", coluna_status_range]
    faltantes = [c for c in colunas_obrigatorias if c not in df.columns]
    if faltantes:
        raise KeyError(f"Colunas ausentes para o teste de Persist: {faltantes}")

    if not pd.api.types.is_datetime64_any_dtype(df["data_hora"]):
        df["data_hora"] = pd.to_datetime(df["data_hora"])
    df = df.sort_values(["codigo_estacao", "data_hora"]).reset_index(drop=True)

    if df_regiao_estacao is not None:
        mapa_regiao = df_regiao_estacao.set_index("codigo_estacao")["regiao"]
        regiao_estacao = df["codigo_estacao"].map(mapa_regiao)
        janela_estacao = (
            regiao_estacao.map(JANELA_POR_REGIAO).fillna(JANELA_PADRAO_FALLBACK).astype(int)
        )
    else:
        janela_estacao = pd.Series(JANELA_PADRAO_FALLBACK, index=df.index)

    grupo = df.groupby("codigo_estacao")["nivel"]
    std_ref = grupo.transform("std") * fator_referencia

    # Janela por estacao nao e constante -- precisa iterar por grupo (mais
    # lento que .transform direto, mas necessario: cada estacao pode ter
    # um tamanho de janela diferente, vindo da regiao dela).
    std_movel = pd.Series(index=df.index, dtype=float)
    gap_janela = pd.Series(index=df.index, dtype=float)
    for _, indices in df.groupby("codigo_estacao").groups.items():
        janela = int(janela_estacao.loc[indices].iloc[0])
        std_movel.loc[indices] = df.loc[indices, "nivel"].rolling(janela).std().values
        gap_janela.loc[indices] = (
            df.loc[indices, "gap_temporal"].astype(float).rolling(janela).max().values
        )

    # Duas causas diferentes de "não deu pra calcular o desvio da janela móvel",
    # com rótulos diferentes (correção de 29/09/2026 -- antes as duas caíam em
    # "nulo", inclusive a segunda, que tem nível presente e não é "sem dado"):
    #   sem_historico_serie : a série INTEIRA da estação não tem desvio-padrão
    #                         (menos de 2 leituras de nível válidas no período
    #                         inteiro) -- não é um problema temporário, então
    #                         continua "nulo".
    #   janela_incompleta   : a série da estação está OK, mas ESTA leitura
    #                         ainda não tem as `janela` leituras anteriores
    #                         acumuladas (é o começo da série de cada estação)
    #                         -- o nível está presente, só falta histórico;
    #                         antes virava "nulo" por engano, agora
    #                         "Teste não realizado", igual à lacuna de dados
    #                         na janela (mesmo efeito na nota -- nenhuma delas
    #                         entra em RESULTADO_FINAL_PERSIST -- só o rótulo
    #                         muda, pra não parecer que faltou o dado).
    sem_historico_serie = std_ref.isna()
    janela_incompleta = std_ref.notna() & std_movel.isna()
    suspeito = (std_movel < std_ref) | (std_ref == 0)
    nulo_no_range = df[coluna_status_range] == "nulo"
    nao_realizado_por_range = (~nulo_no_range) & (df[coluna_status_range] != "aprovado")

    condicoes = [nulo_no_range, nao_realizado_por_range, gap_janela == 1,
                sem_historico_serie, janela_incompleta, suspeito]
    rotulos = ["nulo", "Teste não realizado", "Teste não realizado",
              "nulo", "Teste não realizado", "reprovado"]
    df["status_nivel_persist"] = np.select(condicoes, rotulos, default="aprovado")
    df["janela_persist_usada"] = janela_estacao

    return df


def montar_tabela_cota(df_final, coluna_status_range="status_nivel_range"):
    """codigo_estacao, data (= data_hora, por leitura), dado_bruto_nivel,
    status_nivel_range (3 categorias: aprovado/reprovado/nulo) e
    status_nivel_persist (4 categorias: aprovado/reprovado/nulo/'Teste
    não realizado'), lado a lado, sem fusao entre os dois testes.
    flag_range_cota, dado_consistido_nivel_range, flag_persist_cota e
    dado_consistido_nivel_persist NAO existem mais (eram redundantes)."""
    saida = df_final.rename(columns={"data_hora": "data", "nivel": "dado_bruto_nivel"})
    colunas = [
        "codigo_estacao", "data", "dado_bruto_nivel",
        coluna_status_range, "status_nivel_persist",
    ]
    return saida[colunas]
