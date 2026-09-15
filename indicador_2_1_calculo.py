"""
Descrição: calcula o indicador 2.1 (atraso na transmissão de dados
hidrológicos) a partir da captura da API nova (rota Detalhada). Módulo de
cálculo puro -- a geração de imagem fica em exportar_imagem_indicador_2_1.py,
que importa este módulo (mesma separação que indicador_2_2_calculo.py /
exportar_imagem_indicador_2_2.py já usam).

As constantes de cor (COR_SEM_ATRASO/COR_COM_ATRASO/COR_NAO_RECEBIDO) e de
legenda (LEGENDA_64/LEGENDA_44) moram AQUI de propósito, e não em
exportar_imagem_indicador_2_1.py: este módulo não importa matplotlib, então
indicador_2_1_html.py (usado todo dia pelo rodar_diario_hidro.py, sem
gerar nenhum PNG) pode importar essas constantes sem precisar de
matplotlib instalado. Foi exatamente essa dependência acidental (html ->
exportar_imagem -> matplotlib) que quebrou a primeira rodada real do
Actions em 09/09, porque matplotlib nunca esteve no requirements.txt (só
existia no Colab por vir pré-instalado lá).

Fórmula oficial (texto do contrato): Resultado (%) = pacotes recebidos sem
atraso / total de pacotes previsto no PA × 100. "Total previsto" é teórico
(nº de estações × pacotes/dia × dias do período) -- inclui estações que não
mandaram nada, e por isso é sempre calculado com UMA fórmula só, aplicada a
dois universos de estação diferentes (64 e 44), em vez de duas definições
distintas que davam número incoerente entre si (ver checklist/contexto do
projeto pra esse histórico).

Conexões do Pipeline:
- Entradas: estacao_detalhada_XXXXXXXX.csv (config.PASTA_TELEMETRIA_DETALHADA_ID,
  gerado por orquestrador_telemetria_detalhada.py) e fato_disponibilidade.csv
  (config.PASTA_RELATORIOS_ID, mesmo universo de 64 estações do indicador 2.2).
- Saídas: DataFrame de pacotes consumido por exportar_imagem_indicador_2_1.py
  e por rodar_diario_hidro.py; fato_att_api_nova.csv salvo em
  config.PASTA_RELATORIOS_ID (RETRATO DO DIA -- reescrito a cada rodada, não
  acumulado; até 10/09 esse arquivo se chamava fato_ultima_atualizacao_estacao.csv
  e era acrescentado a cada rodada -- renomeado e trocado pra reescrita porque
  nenhum outro script lê esse arquivo de volta, então o histórico acumulado só
  crescia sem ser consultado).

Funções:
- pontuacao_cd: converte um percentual bruto na pontuação 0-10 (reaproveita
  a tabela do indicador_2_2_calculo.py -- é a mesma do 2.1/2.2).
- carregar_universo_64: lê fato_disponibilidade.csv e devolve a lista de
  códigos de estação (mesmo escopo do 2.2, já sem as 3 retiradas de operação).
- carregar_pacotes_telemetria_detalhada: lê e reduz ao grão de pacote os
  estacao_detalhada_*.csv da API nova.
- calcular_cd_2_1: calcula o Resultado/CD pra um universo de estações.
- gerar_fato_ultima_atualizacao: monta o relatório de última atualização
  por estação, pra identificar quem está falhando.

Uso (Colab):
    import config, drive_io
    from indicador_2_1_calculo import (
        carregar_universo_64, carregar_pacotes_telemetria_detalhada,
        calcular_cd_2_1, gerar_fato_ultima_atualizacao,
    )

    servico = drive_io.conectar_drive("CHAVE.json")
    estacoes_64 = carregar_universo_64(servico)
    df_pacotes = carregar_pacotes_telemetria_detalhada(servico, config.PASTA_TELEMETRIA_DETALHADA_ID)
    estacoes_44 = sorted(df_pacotes["codigo_estacao"].unique().tolist())

    resultado_64 = calcular_cd_2_1(df_pacotes, estacoes_64, dias_periodo=30)
    resultado_44 = calcular_cd_2_1(df_pacotes, estacoes_44, dias_periodo=30)
"""

import pandas as pd

import config
import drive_io
import indicador_2_2_calculo as ind22  # reaproveita TABELA_CD_2_2 / pontuar_percentual -- mesma tabela do 2.1

NOME_FATO_DISPONIBILIDADE = "fato_disponibilidade.csv"
NOME_FATO_ULTIMA_ATUALIZACAO = "fato_att_api_nova.csv"

COR_SEM_ATRASO = "#1c3f66"
COR_COM_ATRASO = "#7ba3c9"
COR_NAO_RECEBIDO = "#c9d6e3"

LEGENDA_64 = "64 estações (20 sem dados recebidos no intervalo de tempo utilizado)"
LEGENDA_44 = "44 estações com dados recebidos dentro do intervalo de tempo utilizado"


def pontuacao_cd(resultado_pct: float) -> int:
    """Mesma tabela de CD do 2.1/2.2 que já existe em indicador_2_2_calculo.py."""
    return ind22.pontuar_percentual(resultado_pct)


def carregar_universo_64(servico) -> list:
    """Lê fato_disponibilidade.csv (config.PASTA_RELATORIOS_ID) e devolve os
    códigos de estação de lá -- mesmo universo do indicador 2.2, que já
    exclui as 3 estações "Plu e Flu" retiradas de operação (Rubelita,
    Fazenda Cajueiro, Ipanema). Usar essa lista em vez de uma lista separada
    garante que o 2.1 nunca diverge do 2.2 nesse ponto."""
    fato_disponibilidade = drive_io.ler_csv(servico, NOME_FATO_DISPONIBILIDADE, config.PASTA_RELATORIOS_ID)
    if fato_disponibilidade is None:
        raise RuntimeError(f"{NOME_FATO_DISPONIBILIDADE} ainda não existe no Drive.")
    fato_disponibilidade["codigo_estacao"] = fato_disponibilidade["codigo_estacao"].astype(str).str.zfill(8)
    return sorted(fato_disponibilidade["codigo_estacao"].unique().tolist())


def carregar_pacotes_telemetria_detalhada(servico, pasta_id):
    """Lê TODOS os estacao_detalhada_XXXXXXXX.csv da pasta da API nova,
    concatena, e reduz ao grão de PACOTE: agrupa por (codigo_estacao,
    Data_Atualizacao) -- cada grupo é um lote/pacote de envio -- e fica só
    com a leitura mais recente de cada grupo (maior Data_Hora_Medicao), que
    é a que define o atraso do pacote.

    Deduplica por nome de arquivo (arquivos duplicados na pasta, se
    houver, são lidos só 1x) e por (codigoestacao, Data_Hora_Medicao)
    dentro do conteúdo -- mesma proteção que pegou o bug real de
    total_recebido > total_previsto na primeira rodada de testes."""
    arquivos = drive_io.listar_arquivos(servico, pasta_id)
    nomes_brutos = [
        a["name"] for a in arquivos
        if a["name"].startswith("estacao_detalhada_") and a["name"].endswith(".csv")
    ]
    nomes_estacao = sorted(set(nomes_brutos))
    if len(nomes_brutos) != len(nomes_estacao):
        from collections import Counter
        repetidos = {n: c for n, c in Counter(nomes_brutos).items() if c > 1}
        print(f"AVISO: {len(nomes_brutos) - len(nomes_estacao)} arquivo(s) com nome duplicado na "
              f"pasta (lidos só 1x cada, vale limpar no Drive): {repetidos}")

    dfs = []
    for nome in nomes_estacao:
        df = drive_io.ler_csv(servico, nome, pasta_id)
        if df is not None and not df.empty:
            dfs.append(df)

    if not dfs:
        raise RuntimeError(f"Nenhum estacao_detalhada_*.csv encontrado em {pasta_id}")

    df_leituras = pd.concat(dfs, ignore_index=True)
    total_antes = len(df_leituras)
    df_leituras = df_leituras.drop_duplicates(subset=["codigoestacao", "Data_Hora_Medicao"], keep="last")
    if len(df_leituras) != total_antes:
        print(f"Removidas {total_antes - len(df_leituras)} linha(s) duplicada(s) dentro dos arquivos lidos.")

    df_leituras["codigo_estacao"] = df_leituras["codigoestacao"].astype(str).str.zfill(8)
    df_leituras["Data_Hora_Medicao"] = pd.to_datetime(
        df_leituras["Data_Hora_Medicao"].astype(str).str.replace(r"\.\d+$", "", regex=True),
        format="%Y-%m-%d %H:%M:%S", errors="coerce",
    )
    df_leituras["Data_Atualizacao"] = pd.to_datetime(
        df_leituras["Data_Atualizacao"].astype(str).str.replace(r"\.\d+$", "", regex=True),
        format="%Y-%m-%d %H:%M:%S", errors="coerce",
    )

    idx_mais_recente = (
        df_leituras.groupby(["codigo_estacao", "Data_Atualizacao"])["Data_Hora_Medicao"].idxmax()
    )
    df_pacotes = df_leituras.loc[idx_mais_recente].reset_index(drop=True)
    df_pacotes["atraso_min"] = (
        (df_pacotes["Data_Atualizacao"] - df_pacotes["Data_Hora_Medicao"]).dt.total_seconds() / 60
    )

    return df_pacotes[["codigo_estacao", "Data_Atualizacao", "Data_Hora_Medicao", "atraso_min"]]


def calcular_cd_2_1(df_pacotes: pd.DataFrame, estacoes_universo: list, dias_periodo: int,
                     limite_atraso_min: int = 30, pacotes_por_dia: int = 24) -> dict:
    """Calcula o CD do indicador 2.1 pra um universo de estações específico.
    Ver docstring do módulo pra fórmula oficial e o motivo de "total
    previsto" ser sempre teórico (inclui quem não mandou nada)."""
    estacoes_universo = [str(e).zfill(8) for e in estacoes_universo]
    df = df_pacotes[df_pacotes["codigo_estacao"].isin(estacoes_universo)]

    total_previsto = len(estacoes_universo) * pacotes_por_dia * dias_periodo
    recebido_sem_atraso = int((df["atraso_min"] <= limite_atraso_min).sum())
    recebido_com_atraso = int((df["atraso_min"] > limite_atraso_min).sum())
    total_recebido = recebido_sem_atraso + recebido_com_atraso

    if total_recebido > total_previsto:
        raise AssertionError(
            f"total_recebido ({total_recebido}) > total_previsto ({total_previsto}) -- "
            f"confira dias_periodo ({dias_periodo}) e se df_pacotes já está reduzido a "
            f"1 linha por pacote (groupby + idxmax), não por leitura individual."
        )
    nao_recebido = total_previsto - total_recebido

    resultado_pct = (recebido_sem_atraso / total_previsto) * 100 if total_previsto else 0.0

    return {
        "n_estacoes": len(estacoes_universo),
        "total_previsto": total_previsto,
        "recebido_sem_atraso": recebido_sem_atraso,
        "recebido_com_atraso": recebido_com_atraso,
        "nao_recebido": nao_recebido,
        "resultado_pct": resultado_pct,
        "cd": pontuacao_cd(resultado_pct),
    }


def gerar_fato_ultima_atualizacao(df_pacotes: pd.DataFrame, estacoes_universo: list,
                                   data_pipeline=None) -> pd.DataFrame:
    """Monta 1 linha por estação (do universo passado) com a última leitura
    já vista dela, pra identificar quem parou de mandar dado. Estação sem
    nenhum dado no período entra com tem_dado_no_periodo=False e datas em
    branco -- não é erro, é a mesma estação já conhecida como muda.

    NOTA (10/09): esse relatório é o retrato do dia -- salvar_fato_ultima_atualizacao()
    reescreve fato_att_api_nova.csv a cada rodada, não acumula histórico dia
    a dia (até 10/09 acumulava, via drive_io.acrescentar_linhas; trocado pra
    reescrita porque nenhum outro script lê o arquivo de volta, e o campo
    dias_sem_atualizacao já carrega, sozinho, a informação de "há quanto
    tempo" sem precisar do histórico completo)."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    if data_pipeline is None:
        data_pipeline = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

    estacoes_universo = sorted(set(str(e).zfill(8) for e in estacoes_universo))

    idx_ultima = df_pacotes.groupby("codigo_estacao")["Data_Hora_Medicao"].idxmax()
    ultima_por_estacao = df_pacotes.loc[idx_ultima].set_index("codigo_estacao")

    linhas = []
    for codigo in estacoes_universo:
        if codigo in ultima_por_estacao.index:
            ultima_medicao = ultima_por_estacao.loc[codigo, "Data_Hora_Medicao"]
            ultima_atualizacao = ultima_por_estacao.loc[codigo, "Data_Atualizacao"]
            dias_sem_atualizacao = (pd.Timestamp(data_pipeline) - ultima_medicao.normalize()).days
            tem_dado = True
        else:
            ultima_medicao = pd.NaT
            ultima_atualizacao = pd.NaT
            dias_sem_atualizacao = None
            tem_dado = False

        linhas.append({
            "data_pipeline": data_pipeline,
            "codigo_estacao": codigo,
            "ultima_data_hora_medicao": ultima_medicao,
            "ultima_data_atualizacao": ultima_atualizacao,
            "dias_sem_atualizacao": dias_sem_atualizacao,
            "tem_dado_no_periodo": tem_dado,
        })

    return pd.DataFrame(linhas)


def salvar_fato_ultima_atualizacao(servico, df_fato_ultima_atualizacao: pd.DataFrame):
    """Salva fato_att_api_nova.csv no Drive (config.PASTA_RELATORIOS_ID) --
    REESCREVE o arquivo (retrato do dia), não acumula (ver nota em
    gerar_fato_ultima_atualizacao)."""
    drive_io.salvar_csv(
        servico, df_fato_ultima_atualizacao, NOME_FATO_ULTIMA_ATUALIZACAO, config.PASTA_RELATORIOS_ID
    )
