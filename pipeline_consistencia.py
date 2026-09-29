"""
Descrição: orquestra, estação por estação, (1) a disponibilidade diária
(indicador 2.2) e (2) os testes de consistência do INDICADOR 2.8, e no
final grava os relatórios consolidados no Drive.

VERSÃO NOVA (Fase 1b, 27/09/2026) -- substitui o pipeline_consistencia.py
do repositório. O que MUDOU e o que NÃO mudou:
- NÃO mudou: etapa04_lacunas (disponibilidade, histórico completo) ->
  fato_disponibilidade.csv; fato_att_api_historica.csv;
  a assinatura rodar_para_todas_estacoes(caminho_chave_json, inicio, limite)
  que o rodar_diario_hidro.py chama.
- MUDOU: os testes antigos (etapa01_teste_precipitacao_range,
  etapa02_step, etapa03_persist) saem; entram os do 2.8
  (indicador_2_8_calculo.py -> etapa01_teste_chuva, etapa_range_cota_zscore,
  etapa03_persist_regional). O teste de STEP fica DESLIGADO.
  Os testes do 2.8 rodam só no período do Contrato de Gestão
  (config_cg.DATA_INICIO_CG_HIDRO em diante), como no rodar_colab.
- Planilhas Google do Looker: NÃO são mais geradas (27/09).
- fato_consistencia.csv: MESMO formato de colunas de
  antes (data_execucao, codigo_estacao, teste, flag, percentual), mas agora
  com os testes do 2.8 (teste = status_chuva / status_nivel_range /
  status_nivel_persist). Gráficos do Looker que filtravam pelos nomes
  antigos (flag_precipitacao, flag_step_cota...) precisam ser ajustados.
- Os antigos estacao_XXXXXXXX_flags.parquet deixam de ser atualizados; o
  detalhe por leitura do 2.8 fica num único indicador_2_8_leituras.parquet.
- NOVOS: indicador_2_8_resumo.csv e indicador_2_8_por_estacao.csv (lidos
  pelo dashboard).

Conexões do Pipeline:
- Entradas: estacao_XXXXXXXX.csv (config.PASTA_ESTACOES_ID), dim_estacao.csv
  (config.PASTA_RELATORIOS_ID), valores_min_max.csv (config.PASTA_DATA_ID),
  frente1.csv (via orquestrador). Earth Engine (CHIRPS), opcional.
- Saídas (config.PASTA_RELATORIOS_ID): fato_disponibilidade.csv,
  fato_consistencia.csv, fato_att_api_historica.csv,
  indicador_2_8_resumo.csv, indicador_2_8_por_estacao.csv,
  indicador_2_8_leituras.parquet.

Funções:
- extrair_ultima_atualizacao / atualizar_relatorio: iguais à versão anterior.
- rodar_para_todas_estacoes: percorre as estações e grava tudo.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config
import drive_io
import etapa04_lacunas as etapa04
import fato_consistencia_estacao as fc
import indicador_2_8_calculo as ind28

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")

NOME_RELATORIO_CONSISTENCIA = "fato_consistencia.csv"
NOME_RELATORIO_DISPONIBILIDADE = "fato_disponibilidade.csv"
NOME_FATO_ULTIMA_ATUALIZACAO_2_2 = "fato_att_api_historica.csv"
# Planilhas Google do Looker (fato_consistencia_dashboard e
# fato_disponibilidade_dashboard): DEIXARAM DE SER GERADAS (decisão de
# 27/09). As que já existem no Drive ficam paradas na última versão.


def extrair_ultima_atualizacao(df_estacao, codigo_estacao, data_pipeline):
    """Igual à versão anterior: última leitura da estação na API histórica."""
    ultima_leitura = df_estacao["data_hora"].max()
    dias_sem_atualizacao = (pd.Timestamp(data_pipeline) - ultima_leitura.normalize()).days
    return {
        "data_pipeline": data_pipeline,
        "codigo_estacao": codigo_estacao,
        "ultima_leitura": ultima_leitura,
        "dias_sem_atualizacao": dias_sem_atualizacao,
    }


def atualizar_relatorio(servico, nome_arquivo, pasta_id, bloco_novo, codigos_atualizados):
    """Igual à versão anterior: upsert por codigo_estacao."""
    existente = drive_io.ler_csv(servico, nome_arquivo, pasta_id)
    if existente is not None and not existente.empty:
        existente["codigo_estacao"] = existente["codigo_estacao"].astype(str).str.zfill(8)
        if "data_dia" in existente.columns:
            existente["data_dia"] = pd.to_datetime(existente["data_dia"], format="mixed")
        codigos_atualizados = [str(c).zfill(8) for c in codigos_atualizados]
        existente = existente[~existente["codigo_estacao"].isin(codigos_atualizados)]
        final = pd.concat([existente, bloco_novo], ignore_index=True)
    else:
        final = bloco_novo
    drive_io.salvar_csv(servico, final, nome_arquivo, pasta_id)
    return final


def rodar_para_todas_estacoes(caminho_chave_json, inicio=0, limite=None, salvar_no_drive=True):
    """Percorre as estações da Frente 1: disponibilidade (2.2) + testes do 2.8.

    `salvar_no_drive=False` roda tudo e devolve os resultados SEM gravar
    nada (para teste no Colab). Rodando em lotes (inicio/limite), os
    arquivos do 2.8 não são gravados -- a soma da rede exige todas as
    estações de uma vez."""
    import orquestrador

    servico = drive_io.conectar_drive(caminho_chave_json)
    codigos = orquestrador.carregar_lista_estacoes(servico)
    lote_completo = inicio == 0 and limite is None
    codigos = codigos[inicio: inicio + limite] if limite is not None else codigos[inicio:]

    data_execucao = datetime.now(FUSO_BRASIL)
    data_pipeline = data_execucao.date()

    # ---- entradas do 2.8 ----
    print("Preparando o indicador 2.8...")
    import config_cg
    config_cg.carregar_exclusoes_do_drive(servico)
    dim = ind28.preparar_dim(drive_io.ler_csv(servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID))
    df_min_max = ind28.carregar_valores_min_max(servico)
    df_regiao = dim[["codigo_estacao", "regiao"]] if "regiao" in dim.columns else None
    if df_regiao is None:
        print("  dim_estacao.csv sem coluna 'regiao' -- Persist usa a janela padrão (etapa03_persist_regional).")
    # Earth Engine/CHIRPS não é mais inicializado aqui -- substituído pelo
    # MERGE (captacao_merge.py) desde 28/09/2026, que não precisa de conta
    # nem de projeto (ver decisoes_e_progresso.md). ind28.inicializar_earth_engine
    # continua disponível, dormente, caso seja preciso voltar ao CHIRPS.

    resumos_disponibilidade, resumos_ultima = [], []
    codigos_processados, sem_dado = [], []
    dfs_chuva, tabelas_nivel = {}, []
    dfs_periodo = {}  # guardado para o fato detalhado (chuva x nível), montado após o MERGE

    for indice, codigo in enumerate(codigos, start=1):
        cod8 = str(codigo).zfill(8)
        print(f"[{indice}/{len(codigos)}] Estacao {cod8}")
        try:
            df_estacao = drive_io.ler_csv(servico, f"estacao_{cod8}.csv", config.PASTA_ESTACOES_ID)
            if df_estacao is None or df_estacao.empty:
                print("  Sem dados consolidados ainda -- pulando.")
                sem_dado.append(cod8)
                continue
            df_estacao["data_hora"] = pd.to_datetime(df_estacao["data_hora"])
            df_estacao["codigo_estacao"] = df_estacao["codigo_estacao"].astype(str).str.zfill(8)

            # (1) disponibilidade -- histórico completo, igual a antes
            disponibilidade = etapa04.calcular_disponibilidade(df_estacao, data_fim_grade=data_execucao)
            disponibilidade.insert(0, "data_execucao", data_execucao)
            resumos_disponibilidade.append(disponibilidade)
            resumos_ultima.append(extrair_ultima_atualizacao(df_estacao, cod8, data_pipeline))
            codigos_processados.append(codigo)

            # (2) testes do 2.8 -- só no período do Contrato de Gestão
            df_periodo = ind28.recortar_periodo(df_estacao, data_pipeline)
            if df_periodo.empty:
                sem_dado.append(cod8)
                print("  Sem leitura no período do 2.8.")
                continue
            entra_chuva, entra_nivel = ind28.universo_da_estacao(cod8, dim)
            if entra_chuva:
                dfs_chuva[cod8] = ind28.testar_chuva(df_periodo)
            if entra_nivel:
                tabelas_nivel.append(ind28.testar_nivel(df_periodo, df_min_max, df_regiao))
            if entra_chuva or entra_nivel:
                dfs_periodo[cod8] = df_periodo
            print(f"  OK -- 2.8: chuva={'sim' if entra_chuva else 'não'}, nível={'sim' if entra_nivel else 'não'}.")
            del df_estacao
        except Exception as erro:  # noqa: BLE001
            print(f"  ERRO: {type(erro).__name__}: {erro}")

    if not codigos_processados:
        print("Nenhuma estacao processada.")
        return None

    # ---- 2.8: MERGE (chuva x satélite), tabela final, resumo ----
    print("\nConsolidando o indicador 2.8 (soma da rede)...")
    tabela_chuva, merge_ok, fato_merge = ind28.aplicar_merge(dfs_chuva, dim, data_pipeline, servico, salvar_no_drive)
    tabela_final = ind28.montar_tabela_final(tabela_chuva, tabelas_nivel)
    resumo_28, por_estacao_28 = ind28.resumir(tabela_final, data_execucao, data_pipeline, sem_dado, merge_ok)
    print(resumo_28[["medida", "aprovados", "avaliados", "percentual", "nota", "n_estacoes"]].to_string(index=False))

    # ---- Fato detalhado por leitura (chuva x nível), para a aba "Consistência
    # por Estação" e para planilhas de apoio -- NÃO entra na nota nem nos
    # gráficos oficiais do 2.8; ver fato_consistencia_estacao.py.
    print("\nMontando o fato detalhado de consistência (chuva x nível, por leitura)...")
    colunas_fm = ["codigo_estacao", "data_dia", "chuva_12z_mm", "chuva_merge_mm", "divergencia_merge"]
    fatos_estacao = []
    for cod8, df_periodo in dfs_periodo.items():
        entra_chuva, entra_nivel = ind28.universo_da_estacao(cod8, dim)
        fm = (fato_merge[fato_merge["codigo_estacao"] == cod8] if fato_merge is not None and not fato_merge.empty
              else pd.DataFrame(columns=colunas_fm))
        try:
            fato = fc.montar_fato_estacao(df_periodo, df_min_max, df_regiao, fm, entra_chuva, entra_nivel)
            if fato is not None:
                fatos_estacao.append(fato)
        except Exception as erro:  # noqa: BLE001
            print(f"  AVISO: fato detalhado de {cod8} falhou ({type(erro).__name__}: {erro}) -- seguindo sem ela.")
    fato_completo = fc.montar_fato_completo(fatos_estacao)
    print(f"  {len(fato_completo)} linhas ({fato_completo['codigo_estacao'].nunique() if len(fato_completo) else 0} estações).")

    relatorio_disponibilidade = pd.concat(resumos_disponibilidade, ignore_index=True)
    relatorio_ultima = pd.DataFrame(resumos_ultima)
    relatorio_consistencia = ind28.resumo_longo_para_looker(tabela_final, data_execucao)

    resultados = {
        "fato_disponibilidade_bloco": relatorio_disponibilidade,
        "tabela_2_8": tabela_final,
        "resumo_2_8": resumo_28,
        "por_estacao_2_8": por_estacao_28,
        "fato_consistencia_estacao": fato_completo,
    }
    if not salvar_no_drive:
        print("\nsalvar_no_drive=False -- nada foi gravado no Drive.")
        return resultados

    atualizar_relatorio(servico, NOME_RELATORIO_DISPONIBILIDADE, config.PASTA_RELATORIOS_ID,
                                                relatorio_disponibilidade, codigos_processados)
    drive_io.salvar_csv(servico, relatorio_ultima, NOME_FATO_ULTIMA_ATUALIZACAO_2_2, config.PASTA_RELATORIOS_ID)

    if lote_completo:
        consistencia_final = relatorio_consistencia
        drive_io.salvar_csv(servico, consistencia_final, NOME_RELATORIO_CONSISTENCIA, config.PASTA_RELATORIOS_ID)
        drive_io.salvar_csv(servico, resumo_28, ind28.NOME_RESUMO, config.PASTA_RELATORIOS_ID)
        drive_io.salvar_csv(servico, por_estacao_28, ind28.NOME_POR_ESTACAO, config.PASTA_RELATORIOS_ID)
        drive_io.salvar_parquet(servico, tabela_final, ind28.NOME_LEITURAS, config.PASTA_RELATORIOS_ID)
        if fato_merge is not None and not fato_merge.empty:
            drive_io.salvar_csv(servico, fato_merge, ind28.captacao_merge.NOME_RELATORIO_FATO, config.PASTA_RELATORIOS_ID)
            print(f"  Relatório do MERGE salvo: {ind28.captacao_merge.NOME_RELATORIO_FATO} ({len(fato_merge)} estação-dias).")
        if not fato_completo.empty:
            drive_io.salvar_csv(servico, fato_completo, fc.NOME_ARQUIVO_FATO, config.PASTA_RELATORIOS_ID)
            print(f"  Fato de consistência por estação salvo: {fc.NOME_ARQUIVO_FATO} ({len(fato_completo)} linhas).")
    else:
        print("AVISO: rodada em lotes -- arquivos do 2.8 NÃO gravados (a soma da rede precisa de todas as estações).")

    print("\nRelatorios atualizados no Drive (disponibilidade e consistencia 2.8).")
    return resultados
