"""
Descrição: orquestra os testes de qualidade em sequência sobre os dados de
cada estação (disponibilidade 2.2 -> precipitação -> range -> step ->
persistência; o Step roda antes do Persist porque este depende da coluna
gap_temporal gerada por aquele). Processa uma estação por vez para não
acumular dados de todas em memória: o detalhe linha a linha é salvo em
Parquet e descartado, ficando só o resumo agregado.

O indicador 2.8 (% de dados consistidos) ainda não é calculado aqui -- o
relatório traz o percentual de cada flag separadamente, no formato longo,
pronto para ser agregado quando a regra de combinação for definida.

Conexões do Pipeline:
- Entradas: estacao_XXXXXXXX.csv (config.PASTA_ESTACOES_ID, gerado por
  orquestrador.py); usa etapa01_teste_precipitacao_range.py,
  etapa02_step.py, etapa03_persist.py, etapa04_lacunas.py e drive_io.py.
- Saídas: estacao_XXXXXXXX_flags.parquet por estação
  (config.PASTA_ESTACOES_FLAGS_ID), fato_consistencia.csv e
  fato_disponibilidade.csv (config.PASTA_RELATORIOS_ID) + planilhas Google
  equivalentes para o Looker Studio; fato_att_api_historica.csv
  (config.PASTA_RELATORIOS_ID, NOVO 10/09 -- retrato do dia, reescrito a
  cada rodada, última leitura de cada estação na API antiga/histórica --
  equivalente ao fato_att_api_nova.csv do indicador 2.1, mas cada um com
  sua própria fonte de dado, sem cruzar as duas). Chamado por
  rodar_diario_hidro.py.

Funções:
- rodar_pipeline_consistencia: roda a sequência completa de testes sobre uma estação.
- resumir_flags: resume as flags de uma estação no formato longo (teste x categoria x percentual).
- extrair_ultima_atualizacao: monta 1 linha com a última leitura de uma estação na API histórica.
- atualizar_relatorio: faz upsert das linhas de um relatório no Drive por código de estação.
- rodar_para_todas_estacoes: percorre todas as estações, salva o detalhe em Parquet e consolida os relatórios.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config
import drive_io
import etapa01_teste_precipitacao_range as etapa01
import etapa02_step as etapa02
import etapa03_persist as etapa03
import etapa04_lacunas as etapa04

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")

COLUNAS_FLAG = [
    "flag_precipitacao",
    "flag_range_cota",
    "flag_range_vazao",
    "flag_step_cota",
    "flag_step_vazao",
    "flag_persist_cota",
    "flag_persist_vazao",
]

NOME_RELATORIO_CONSISTENCIA = "fato_consistencia.csv"
NOME_RELATORIO_DISPONIBILIDADE = "fato_disponibilidade.csv"
NOME_FATO_ULTIMA_ATUALIZACAO_2_2 = "fato_att_api_historica.csv"

# Nomes das Planilhas Google (nao .csv) que alimentam o Data Studio.

NOME_PLANILHA_CONSISTENCIA_DASHBOARD = "fato_consistencia_dashboard"
NOME_PLANILHA_DISPONIBILIDADE_DASHBOARD = "fato_disponibilidade_dashboard"


def rodar_pipeline_consistencia(df_estacao, data_execucao=None):
    """Roda a sequencia completa de testes sobre os dados de UMA estacao.
    Devolve (registros_com_flags, disponibilidade_diaria).

    data_execucao (ajuste 10/09): data/hora de referencia repassada pra
    etapa04.calcular_disponibilidade (data_fim_grade) -- normalmente a data
    de execucao do pipeline, pra uma estacao que parou de transmitir
    continuar contando dias de lacuna ate a rodada atual, em vez de "sumir"
    do relatorio de disponibilidade no dia da ultima leitura dela. Se None,
    etapa04 usa a data de hoje como padrao (uso standalone/teste)."""
    disponibilidade = etapa04.calcular_disponibilidade(df_estacao, data_fim_grade=data_execucao)

    registros = etapa01.teste_precipitacao(df_estacao)
    registros = etapa01.teste_range(registros)
    registros = etapa02.teste_step(registros)
    registros = etapa03.teste_persistencia(registros)

    return registros, disponibilidade


def resumir_flags(registros_estacao, codigo_estacao, data_execucao):
    """Resume as flags de UMA estacao no formato longo: uma linha por
    combinacao teste x categoria de flag, com o percentual encontrado.

    Isso substitui manter o DataFrame de registros inteiro em memoria -- so
    guardamos o resumo, em vez de arrastar centenas de milhares de linhas de cada estacao ate o final do loop.
    """
    linhas = []
    for coluna_flag in COLUNAS_FLAG:
        if coluna_flag not in registros_estacao.columns:
            continue
        contagem = (
            registros_estacao[coluna_flag]
            .value_counts(normalize=True)
            .mul(100)
            .round(2)
        )
        for flag, percentual in contagem.items():
            linhas.append(
                {
                    "data_execucao": data_execucao,
                    "codigo_estacao": codigo_estacao,
                    "teste": coluna_flag,
                    "flag": flag,
                    "percentual": percentual,
                }
            )
    return pd.DataFrame(linhas)


def extrair_ultima_atualizacao(df_estacao: pd.DataFrame, codigo_estacao: str, data_pipeline) -> dict:
    """Monta 1 linha com a última leitura já vista dessa estação na API
    histórica (antiga) -- reaproveita o df_estacao que já foi carregado pra
    rodar o resto do pipeline de consistência nesta mesma rodada, não lê
    nada de novo do Drive.

    Equivalente ao indicador_2_1_calculo.gerar_fato_ultima_atualizacao(),
    só que mais simples porque a API histórica só tem um timestamp por
    leitura (data_hora) -- a API nova tem Data_Hora_Medicao e
    Data_Atualizacao separados."""
    ultima_leitura = df_estacao["data_hora"].max()
    dias_sem_atualizacao = (pd.Timestamp(data_pipeline) - ultima_leitura.normalize()).days

    return {
        "data_pipeline": data_pipeline,
        "codigo_estacao": codigo_estacao,
        "ultima_leitura": ultima_leitura,
        "dias_sem_atualizacao": dias_sem_atualizacao,
    }


def atualizar_relatorio(servico, nome_arquivo, pasta_id, bloco_novo, codigos_atualizados):
    """Atualiza um relatorio no Drive substituindo SOMENTE as linhas das
    estacoes processadas nesse lote (upsert por codigo_estacao) -- preserva as
    linhas de estacoes de outros lotes que nao foram reprocessadas agora.
    Sem isso, rodar em lotes faria cada lote apagar o resultado do anterior.
    """
    existente = drive_io.ler_csv(servico, nome_arquivo, pasta_id)
    if existente is not None and not existente.empty:
        existente["codigo_estacao"] = existente["codigo_estacao"].astype(str).str.zfill(8)
        if "data_dia" in existente.columns:
            # Ao reler do CSV, a data volta como texto puro -- sem isso ela
            # fica "misturada" com as datas novas (que chegam como datetime
            # de verdade) e o formato degrada a cada rodada de upsert
            # (algumas linhas com hora, outras sem). So se aplica ao
            # fato_disponibilidade.csv -- o de consistencia nao tem essa
            # coluna.
            existente["data_dia"] = pd.to_datetime(existente["data_dia"], format="mixed")

        codigos_atualizados = [str(codigo).zfill(8) for codigo in codigos_atualizados]

        existente = existente[~existente["codigo_estacao"].isin(codigos_atualizados)]
        final = pd.concat([existente, bloco_novo], ignore_index=True)
    else:
        final = bloco_novo

    drive_io.salvar_csv(servico, final, nome_arquivo, pasta_id)
    return final


def rodar_para_todas_estacoes(caminho_chave_json, inicio=0, limite=None):
    """Le a lista de estacoes e roda a pipeline de consistencia uma estacao de
    cada vez. Ao final, atualiza os relatorios consolidados (formato longo)
    no Drive -- so as estacoes processadas nesse lote sao substituidas, o
    resto do relatorio fica intacto. Também reescreve fato_att_api_historica.csv
    (retrato do dia -- última leitura de cada estação processada nesta rodada)."""
    import orquestrador  # reaproveita a leitura da lista de estacoes

    servico = drive_io.conectar_drive(caminho_chave_json)
    codigos = orquestrador.carregar_lista_estacoes(servico)

    if limite is not None:
        codigos = codigos[inicio: inicio + limite]
    else:
        codigos = codigos[inicio:]

    data_execucao = datetime.now(FUSO_BRASIL)
    data_pipeline = data_execucao.date()
    resumos_flags = []
    resumos_disponibilidade = []
    resumos_ultima_atualizacao = []
    codigos_processados = []

    for indice, codigo in enumerate(codigos, start=1):
        codigo_padronizado = str(codigo).zfill(8)
        nome_arquivo = f"estacao_{codigo_padronizado}.csv"
        print(f"[{indice}/{len(codigos)}] Estacao {codigo}")

        try:
            df_estacao = drive_io.ler_csv(servico, nome_arquivo, config.PASTA_ESTACOES_ID)
            if df_estacao is None or df_estacao.empty:
                print("  Sem dados consolidados ainda -- pulando.")
                continue

            df_estacao["data_hora"] = pd.to_datetime(df_estacao["data_hora"])
            df_estacao["codigo_estacao"] = df_estacao["codigo_estacao"].astype(str).str.zfill(8)

            registros, disponibilidade = rodar_pipeline_consistencia(df_estacao, data_execucao=data_execucao)

            # Salva o detalhe por medicao (linha a linha, com todas as flags)
            # no Drive ANTES de descartar da memoria -- sobrescreve o Parquet
            # dessa estacao com a versao recem-recalculada (historico
            # completo, antigo + novo junto).
            drive_io.salvar_parquet(
                servico, registros, f"estacao_{codigo_padronizado}_flags.parquet", config.PASTA_ESTACOES_FLAGS_ID
            )

            resumos_flags.append(resumir_flags(registros, codigo, data_execucao))
            disponibilidade.insert(0, "data_execucao", data_execucao)
            resumos_disponibilidade.append(disponibilidade)
            resumos_ultima_atualizacao.append(
                extrair_ultima_atualizacao(df_estacao, codigo_padronizado, data_pipeline)
            )
            codigos_processados.append(codigo)

            print(f"  OK -- {len(registros)} registros avaliados, detalhe salvo em Parquet.")

            # Descarta explicitamente os dados no nivel de registro dessa
            # estacao antes de seguir para a proxima -- so o resumo (pequeno)
            # continua na memoria. So marcamos como "processado" (para o
            # upsert) depois que o resumo ja foi calculado com sucesso.
            del df_estacao, registros, disponibilidade

        except Exception as erro:
            print(f"  ERRO: {erro}")

    if not resumos_flags:
        print("Nenhuma estacao processada.")
        return

    relatorio_flags = pd.concat(resumos_flags, ignore_index=True)
    relatorio_disponibilidade = pd.concat(resumos_disponibilidade, ignore_index=True)
    relatorio_ultima_atualizacao = pd.DataFrame(resumos_ultima_atualizacao)

    consistencia_final = atualizar_relatorio(
        servico, NOME_RELATORIO_CONSISTENCIA, config.PASTA_RELATORIOS_ID,
        relatorio_flags, codigos_processados,
    )
    disponibilidade_final = atualizar_relatorio(
        servico, NOME_RELATORIO_DISPONIBILIDADE, config.PASTA_RELATORIOS_ID,
        relatorio_disponibilidade, codigos_processados,
    )

    # fato_att_api_historica.csv NAO usa atualizar_relatorio (upsert) -- e
    # reescrito por inteiro a cada rodada, so com o retrato de hoje das
    # estacoes processadas neste lote (mesmo padrao do fato_att_api_nova.csv
    # do indicador 2.1).
    drive_io.salvar_csv(
        servico, relatorio_ultima_atualizacao, NOME_FATO_ULTIMA_ATUALIZACAO_2_2, config.PASTA_RELATORIOS_ID
    )

    # Mantem as Planilhas Google que alimentam o Data Studio sempre com o
    # mesmo conteudo final dos relatorios .csv -- e a unica forma do
    # dashboard atualizar sozinho
    drive_io.salvar_planilha_google(
        servico, consistencia_final, NOME_PLANILHA_CONSISTENCIA_DASHBOARD, config.PASTA_RELATORIOS_ID
    )
    drive_io.salvar_planilha_google(
        servico, disponibilidade_final, NOME_PLANILHA_DISPONIBILIDADE_DASHBOARD, config.PASTA_RELATORIOS_ID
    )

    print("\nRelatorios de consistencia atualizados no Drive (pasta 'relatorios'), CSV e Planilha Google.")
