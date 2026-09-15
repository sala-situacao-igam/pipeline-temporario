"""
Descrição: calcula os indicadores 4.1 (previsões do tempo), 4.2 (alertas
de tempestade severa) e 4.3 (tendência climática) -- contagem e pontuação
(CD) a partir da lista já extraída por extrair_documentos_simge_ingestao.py
(que este módulo importa).

Conexões do Pipeline:
- Entradas: extrair_documentos_simge_ingestao.py (extração bruta).
- Saídas: DataFrames consumidos por indicador_meteorologia.py,
  exportar_imagem_indicador_meteorologia.py e rodar_diario_meteoro.py.

Funções:
- pontuar_percentual_4_1_4_3: converte um percentual na pontuação 0-10 da tabela de CD do 4.1/4.3.
- calcular_cd_4_1: calcula a pontuação (CD) do indicador 4.1 no período.
- calcular_cd_4_3: calcula a pontuação (CD) do indicador 4.3 no período.
- calcular_cd_4_2: calcula a pontuação (CD) do indicador 4.2 no período.
- contar_alertas_4_2: conta os dias com alerta e os alertas individuais no período.
- contar_previsoes_4_1: conta os arquivos de previsão publicados no período.
- contar_tendencia_climatica_4_3: conta os boletins de tendência climática publicados no período.
- dataframe_previsoes_4_1: converte o resultado do 4.1 em DataFrame (uma linha por arquivo).
- dataframe_dias_semana_4_1: converte o resultado do 4.1 em DataFrame por dia da semana.
- dataframe_tendencia_4_3: converte o resultado do 4.3 em DataFrame (uma linha por boletim).
- dataframe_alertas_4_2: converte o resultado do 4.2 em DataFrame (uma linha por dia com alerta).

Uso:
    from extrair_documentos_simge_ingestao import (
        URL_PASTA_PREVISOES_2026,
        URL_PASTA_TENDENCIA_CLIMATICA_2026,
    )
    from extrair_documentos_simge_calculo import (
        contar_previsoes_4_1,
        contar_tendencia_climatica_4_3,
        dataframe_previsoes_4_1,
        dataframe_dias_semana_4_1,
        dataframe_tendencia_4_3,
    )
    import config
    import drive_io

    # Indicador 4.1
    resultado_4_1 = contar_previsoes_4_1(URL_PASTA_PREVISOES_2026, "2026-01-01", "2026-08-31")

    # Indicador 4.3 (só TENDENCIA_CLIMATICA_*, PROGNOSTICO_* fica de fora)
    resultado_4_3 = contar_tendencia_climatica_4_3(URL_PASTA_TENDENCIA_CLIMATICA_2026, "2026-01-01", "2026-08-31")

    # Salvar no Drive (pastas já confirmadas -- mesmo Drive Compartilhado
    # do resto do pipeline, salvar_csv() já é genérico, não precisou de
    # nenhuma função nova no drive_io.py):
    servico = drive_io.conectar_drive("chave_servico.json")
    drive_io.salvar_csv(servico, dataframe_previsoes_4_1(resultado_4_1), "indicador_4_1_previsoes_2026.csv", config.PASTA_PREVISAO_TEMPO_ID)
    drive_io.salvar_csv(servico, dataframe_dias_semana_4_1(resultado_4_1), "indicador_4_1_por_dia_semana_2026.csv", config.PASTA_PREVISAO_TEMPO_ID)
    drive_io.salvar_csv(servico, dataframe_tendencia_4_3(resultado_4_3), "indicador_4_3_tendencia_climatica_2026.csv", config.PASTA_MONITORAMENTO_CLIMATICO_ID)
"""
from collections import defaultdict
from datetime import date

import pandas as pd

from extrair_documentos_simge_ingestao import (
    INSTANCIA_PREVISOES,
    INSTANCIA_TENDENCIA,
    URL_PASTA_PREVISOES_2026,
    URL_PASTA_TENDENCIA_CLIMATICA_2026,
    URL_ALERTAS_TEMPESTADE_SEVERA,
    _coletar_periodo,
    coletar_alertas_periodo,
)

# ---------------------------------------------------------------------
# Pontuação (CD) do indicador 4.1 -- confirmada com a Valéria em 02/09/2026
# ---------------------------------------------------------------------
# Tabela de Calculo de Desempenho (CD) para 4.1/4.3 -- DIFERENTE da
# TABELA_CD_2_2 de indicador_2_2_calculo.py (essa é a do 2.1/2.2, não usar
# aqui). Ordem do mais alto pro mais baixo importa.
TABELA_CD_4_1_4_3 = [
    (100.0, 10),
    (95.0, 8),
    (90.0, 6),
    (0.0, 0),
]

# Feriados/pontos facultativos de 2026 informados pela Valéria (02/09) --
# datas exatas do ano, com os móveis (Sexta-feira Santa, Carnaval, Corpus
# Christi) já resolvidos. ATENÇÃO: essas datas são só de 2026 -- pra rodar
# em 2027 em diante, essa lista precisa ser atualizada (feriados móveis
# mudam de data todo ano).
FERIADOS_NACIONAIS_2026 = [
    ("2026-01-01", "Confraternização Universal"),
    ("2026-04-03", "Sexta-feira Santa"),
    ("2026-04-21", "Tiradentes e Data Magna de MG"),
    ("2026-05-01", "Dia do Trabalho"),
    ("2026-09-07", "Independência do Brasil"),
    ("2026-10-12", "Nossa Senhora Aparecida"),
    ("2026-11-02", "Finados"),
    ("2026-11-15", "Proclamação da República"),
    ("2026-11-20", "Dia da Consciência Negra"),
    ("2026-12-25", "Natal"),
]

# Confirmado com a Valéria (02/09): pontos facultativos também contam como
# "não é dia útil" pro denominador do 4.1 (opção C, contra as opções A/B
# testadas em teste_pontuacao_4_1_v2.py).
PONTOS_FACULTATIVOS_2026 = [
    ("2026-02-17", "Carnaval"),
    ("2026-06-04", "Corpus Christi"),
    ("2026-10-30", "Dia do Servidor Público"),
]


def pontuar_percentual_4_1_4_3(percentual):
    """Converte um percentual bruto (0-100) na pontuação 0-10 da tabela de
    CD do 4.1/4.3 (TABELA_CD_4_1_4_3)."""
    for limite, pontos in TABELA_CD_4_1_4_3:
        if percentual >= limite:
            return pontos
    return 0


def calcular_cd_4_1(resultado_4_1, data_inicio, data_fim):
    """Indicador 4.1 -- pontuação (CD), total simples do período (sem
    quebrar em semana). Denominador = dias úteis do período, excluindo
    feriados nacionais/estaduais e pontos facultativos
    (FERIADOS_NACIONAIS_2026 + PONTOS_FACULTATIVOS_2026 acima).

    `resultado_4_1`: dicionário devolvido por contar_previsoes_4_1().
    `data_inicio`/`data_fim`: mesmo período usado pra chamar contar_previsoes_4_1().

    Devolve um dicionário com dias_uteis, previsoes_publicadas, percentual,
    pontuacao, e feriados_no_periodo (lista dos feriados/facultativos que
    caíram em dia útil dentro do período, pra mostrar de forma transparente
    de onde veio o ajuste no denominador)."""
    todos_dias_uteis = set(pd.bdate_range(data_inicio, data_fim))

    feriados_no_periodo = []
    excluir = set()
    for lista, tipo in [(FERIADOS_NACIONAIS_2026, "Feriado"), (PONTOS_FACULTATIVOS_2026, "Facultativo")]:
        for data_str, rotulo in lista:
            ts = pd.Timestamp(data_str)
            if ts in todos_dias_uteis:
                excluir.add(ts)
                feriados_no_periodo.append({"data": ts.date(), "rotulo": rotulo, "tipo": tipo})
    feriados_no_periodo.sort(key=lambda f: f["data"])

    dias_uteis = len(todos_dias_uteis - excluir)
    previsoes_publicadas = resultado_4_1["total_arquivos"]
    percentual = round(previsoes_publicadas / dias_uteis * 100, 2) if dias_uteis else 0.0
    pontuacao = pontuar_percentual_4_1_4_3(percentual)

    return {
        "dias_uteis": dias_uteis,
        "previsoes_publicadas": previsoes_publicadas,
        "percentual": percentual,
        "pontuacao": pontuacao,
        "feriados_no_periodo": feriados_no_periodo,
    }


def calcular_cd_4_3(resultado_4_3, data_inicio, data_fim):
    """Indicador 4.3 -- pontuação (CD). Apesar de cada boletim
    TENDENCIA_CLIMATICA_* cobrir 3 meses (trimestral, com sobreposição), a
    publicação em si é esperada com frequência mensal -- 1 boletim por
    mês. Denominador = número de meses decorridos no período (contagem de
    meses-calendário entre data_inicio e data_fim, inclusive, mesmo que o
    mês esteja incompleto). Usa a mesma tabela de CD do 4.1
    (TABELA_CD_4_1_4_3).

    `resultado_4_3`: dicionário devolvido por contar_tendencia_climatica_4_3().
    `data_inicio`/`data_fim`: mesmo período usado pra chamar contar_tendencia_climatica_4_3()."""
    inicio = pd.Timestamp(data_inicio)
    fim = pd.Timestamp(data_fim)
    meses_esperados = (fim.year - inicio.year) * 12 + (fim.month - inicio.month) + 1

    boletins_publicados = resultado_4_3["total_boletins"]
    percentual = round(boletins_publicados / meses_esperados * 100, 2) if meses_esperados else 0.0
    pontuacao = pontuar_percentual_4_1_4_3(percentual)

    return {
        "meses_esperados": meses_esperados,
        "boletins_publicados": boletins_publicados,
        "percentual": percentual,
        "pontuacao": pontuacao,
    }


def calcular_cd_4_2(resultado_4_2, data_inicio, data_fim):
    """Indicador 4.2 -- pontuação (CD). "Relatórios diários emitidos" =
    dias com pelo menos 1 alerta publicado (mesma definição usada em
    contar_alertas_4_2()). Denominador = número de dias corridos entre
    data_inicio e data_fim, inclusive (não é dia útil, é todo dia do
    período). Usa a mesma tabela de CD (TABELA_CD_4_1_4_3).

    `resultado_4_2`: dicionário devolvido por contar_alertas_4_2().
    `data_inicio`/`data_fim`: mesmo período usado pra chamar contar_alertas_4_2().

    Devolve um dicionário com dias_no_periodo, relatorios_emitidos,
    percentual, pontuacao."""
    inicio = pd.Timestamp(data_inicio)
    fim = pd.Timestamp(data_fim)
    dias_no_periodo = (fim - inicio).days + 1

    relatorios_emitidos = resultado_4_2["total_dias_com_alerta"]
    percentual = round(relatorios_emitidos / dias_no_periodo * 100, 2) if dias_no_periodo else 0.0
    pontuacao = pontuar_percentual_4_1_4_3(percentual)

    return {
        "dias_no_periodo": dias_no_periodo,
        "relatorios_emitidos": relatorios_emitidos,
        "percentual": percentual,
        "pontuacao": pontuacao,
    }


def contar_alertas_4_2(url_alertas, data_inicio, data_fim):
    """Indicador 4.2 -- "Percentual do Monitoramento Meteorológico e envio
    de alertas realizado". Conta os "relatórios diários" (dias com pelo
    menos 1 alerta publicado em
    https://simge.mg.gov.br/alerta-de-tempestade-severa) e os alertas
    individuais dentro deles. "Número de relatórios diários" = número de
    dias com alerta (não a contagem de alertas individuais -- um dia pode
    ter vários). O percentual/pontuação (CD) fica em calcular_cd_4_2().

    `por_mes_dias`/`por_mes_alertas`: sempre com os 12 meses (janeiro a
    dezembro) do ano de `data_inicio` presentes, com 0 nos meses que ainda
    não chegaram (mesmo padrão de zero-fill de dataframe_dias_semana_4_1()).

    Devolve um dicionário com: total_dias_com_alerta,
    total_alertas_individuais, dias (lista crua, um item por dia, com os
    alertas individuais dentro), por_mes_dias, por_mes_alertas."""
    dias = coletar_alertas_periodo(url_alertas, data_inicio, data_fim)

    ano_referencia = pd.Timestamp(data_inicio).year
    por_mes_dias = {f"{ano_referencia}-{mes:02d}": 0 for mes in range(1, 13)}
    por_mes_alertas = {chave: 0 for chave in por_mes_dias}

    for dia in dias:
        chave = f"{dia['data'].year}-{dia['data'].month:02d}"
        if chave in por_mes_dias:  # só conta no zero-fill se for do ano de referência
            por_mes_dias[chave] += 1
            por_mes_alertas[chave] += len(dia["alertas"])

    return {
        "total_dias_com_alerta": len(dias),
        "total_alertas_individuais": sum(len(d["alertas"]) for d in dias),
        "dias": dias,
        "por_mes_dias": por_mes_dias,
        "por_mes_alertas": por_mes_alertas,
    }


def contar_previsoes_4_1(url_pasta_2026, data_inicio, data_fim, itens_por_pagina=500, max_paginas=5):
    """Indicador 4.1 -- conta os arquivos de previsão publicados no
    período. Devolve um dicionário com:
      - 'total_arquivos': quantos arquivos existem no período (1 por dia
        útil publicado).
      - 'arquivos': lista (datetime_criacao, titulo) ordenada por data.
      - 'por_dia_semana': quantos arquivos caem em cada dia da semana 
        (Segunda...Domingo), mesmo com contagem zero.
      - 'total_previsoes_ponderado_sexta_x3': hipótese de cálculo onde
        cada arquivo de sexta-feira conta como 3 (o boletim de sexta já
        embute as previsões de sábado e domingo) e os demais dias contam
        1. Não é o total oficial -- é uma conta alternativa para decidir
        o critério certo para o numerador do indicador.
    """
    linhas = _coletar_periodo(url_pasta_2026, INSTANCIA_PREVISOES, data_inicio, data_fim, itens_por_pagina, max_paginas)

    dias_semana_pt = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    por_dia_semana = {dia: 0 for dia in dias_semana_pt}  # zero-fill -- inclui sáb/dom mesmo sem nenhum arquivo
    total_ponderado = 0
    for dt_criacao, _titulo in linhas:
        dia_semana = dt_criacao.weekday()  # 0 = segunda ... 6 = domingo
        por_dia_semana[dias_semana_pt[dia_semana]] += 1
        total_ponderado += 3 if dia_semana == 4 else 1  # sexta = índice 4

    return {
        "total_arquivos": len(linhas),
        "arquivos": linhas,
        "por_dia_semana": por_dia_semana,
        "total_previsoes_ponderado_sexta_x3": total_ponderado,
    }


def contar_tendencia_climatica_4_3(url_pasta_2026, data_inicio, data_fim, itens_por_pagina=500, max_paginas=5):
    """Indicador 4.3 -- conta só os boletins TENDENCIA_CLIMATICA_* (PROGNOSTICO_* fica de fora). 
    Devolve:
      - 'total_boletins': quantos TENDENCIA_CLIMATICA_* existem no período.
      - 'boletins': lista (datetime_criacao, titulo) ordenada por data.
      - 'por_mes': quantos boletins foram criados em cada mês/ano (usando
        a data real de criação do arquivo, não o nome do arquivo).
      - 'excluidos_prognostico': lista dos PROGNOSTICO_* encontrados no
        período, só para conferência (não entram na contagem).
    """
    linhas = _coletar_periodo(url_pasta_2026, INSTANCIA_TENDENCIA, data_inicio, data_fim, itens_por_pagina, max_paginas)

    boletins = [(dt, titulo) for dt, titulo in linhas if titulo.upper().startswith("TENDENCIA_CLIMATICA")]
    excluidos = [(dt, titulo) for dt, titulo in linhas if titulo.upper().startswith("PROGNOSTICO")]

    por_mes = defaultdict(int)
    for dt_criacao, _titulo in boletins:
        chave = f"{dt_criacao.year}-{dt_criacao.month:02d}"
        por_mes[chave] += 1

    return {
        "total_boletins": len(boletins),
        "boletins": boletins,
        "por_mes": dict(sorted(por_mes.items())),
        "excluidos_prognostico": excluidos,
    }


# ---------------------------------------------------------------------
# Preparar e salvar no Drive (novo -- 31/08)
# ---------------------------------------------------------------------
# `salvar_csv()` do drive_io.py já é genérico (recebe o ID da pasta como
# parâmetro) -- não precisa de nenhuma função nova nem mudança no
# drive_io.py. Só falta montar o DataFrame a partir do resultado de
# contar_previsoes_4_1()/contar_tendencia_climatica_4_3() e chamar
# salvar_csv() com a pasta certa (config.PASTA_PREVISAO_TEMPO_ID /
# config.PASTA_MONITORAMENTO_CLIMATICO_ID). As duas funções abaixo fazem
# só essa conversão.

def dataframe_previsoes_4_1(resultado):
    """Converte o resultado de contar_previsoes_4_1() num DataFrame pronto
    para salvar (colunas: data_hora_criacao, dia_semana, arquivo)."""
    dias_semana_pt = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    linhas = [
        {
            "data_hora_criacao": dt,
            "dia_semana": dias_semana_pt[dt.weekday()],
            "arquivo": titulo,
        }
        for dt, titulo in resultado["arquivos"]
    ]
    return pd.DataFrame(linhas)


def dataframe_dias_semana_4_1(resultado):
    """DataFrame pronto pra virar gráfico de publicações por dia da
    semana -- os 7 dias sempre aparecem, incluindo sábado e domingo com
    contagem 0. Ordem fixa Segunda->Domingo, não alfabética, pra ficar
    correta num gráfico de barras."""
    dias_semana_pt = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    linhas = [
        {"dia_semana": dia, "total_publicacoes": resultado["por_dia_semana"].get(dia, 0)}
        for dia in dias_semana_pt
    ]
    return pd.DataFrame(linhas)


def dataframe_tendencia_4_3(resultado):
    """Converte o resultado de contar_tendencia_climatica_4_3() num
    DataFrame pronto para salvar (colunas: data_hora_criacao, mes_criacao,
    boletim). Só inclui os TENDENCIA_CLIMATICA_* -- os PROGNOSTICO_*
    excluídos não entram aqui."""
    linhas = [
        {
            "data_hora_criacao": dt,
            "mes_criacao": f"{dt.year}-{dt.month:02d}",
            "boletim": titulo,
        }
        for dt, titulo in resultado["boletins"]
    ]
    return pd.DataFrame(linhas)


def dataframe_alertas_4_2(resultado):
    """Converte o resultado de contar_alertas_4_2() num DataFrame pronto
    para salvar (colunas: data, mes, total_alertas_no_dia, titulo) -- uma
    linha por DIA com alerta (mesma granularidade de dataframe_previsoes_4_1(),
    que tem uma linha por arquivo publicado). `titulo` é o texto bruto do
    título do dia na página do SIMGE (ex.: "Terça-feira, 01 de setembro de
    2026"), só pra referência/conferência."""
    linhas = [
        {
            "data": dia["data"],
            "mes": f"{dia['data'].year}-{dia['data'].month:02d}",
            "total_alertas_no_dia": len(dia["alertas"]),
            "titulo": dia["titulo"],
        }
        for dia in resultado["dias"]
    ]
    return pd.DataFrame(linhas)


