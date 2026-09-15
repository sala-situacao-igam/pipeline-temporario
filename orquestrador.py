"""
Descrição: Passo 1 do pipeline -- ingestão incremental diária das estações
da Frente 1 a partir da API da ANA (isolamento de falhas: um erro numa
estação não interrompe as demais, fica registrado no log de erros).

Conexões do Pipeline:
- Entradas: frente1.csv (Drive, config.PASTA_DATA_ID) e histórico existente
  em config.PASTA_ESTACOES_ID; usa ingestao_ana.py e drive_io.py.
- Saídas: estacao_XXXXXXXX.csv por estação (config.PASTA_ESTACOES_ID),
  log_erros.csv e log_cargas_iniciais.csv (config.PASTA_RELATORIOS_ID).
  Chamado por rodar_diario_hidro.py.

Funções:
- carregar_lista_estacoes: lê e limpa a lista de códigos de estação do frente1.csv.
- processar_estacao: baixa os dados novos de uma estação, funde com o histórico e salva no Drive.
- rodar_pipeline: roda processar_estacao para todas as estações (ou um lote), com isolamento de falhas e logs.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config
import drive_io
import ingestao_ana

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")
DATA_INICIO_PADRAO = "01/01/2014"
NOME_LISTA_ESTACOES = "frente1.csv"


def carregar_lista_estacoes(servico):
    """Le a lista de estacoes ativas a partir do CSV de configuracao no Drive,
    descartando linhas sem codigo (como as linhas 'APV' do frente1.csv)."""
    lista = drive_io.ler_csv(servico, NOME_LISTA_ESTACOES, config.PASTA_DATA_ID, sep=";")
    lista = lista[lista["CÓDIGO IGAM"].notna()]
    # As linhas "APV" (vazias) fazem o pandas ler a coluna como float -- sem
    # passar por int antes do texto, o codigo vira "2042051.0" em vez de
    # "2042051", o que corrompe a consulta na API.
    codigos = (
        lista["CÓDIGO IGAM"].astype(float).astype(int).astype(str).str.strip().tolist()
    )
    return codigos


def processar_estacao(servico, codigo):
    """Processa uma única estação: lê o histórico existente, busca dados
    novos de forma incremental, funde, deduplica, ordena e salva de volta
    no Drive. Devolve um dicionário com o resultado dessa estação (usado
    pelo orquestrador para decidir o que registrar nos logs).

    O nome do arquivo sempre usa codigo.zfill(8) (padrão usado em todo o
    projeto), garantindo que cada estação tenha um único arquivo no Drive."""
    codigo_padronizado = str(codigo).zfill(8)
    nome_arquivo = f"estacao_{codigo_padronizado}.csv"

    dados_existentes = drive_io.ler_csv(servico, nome_arquivo, config.PASTA_ESTACOES_ID)
    carga_inicial = dados_existentes is None

    if not carga_inicial:
        # O CSV nao guarda o tipo da coluna -- precisamos re-tipar apos a leitura.
        dados_existentes["data_hora"] = pd.to_datetime(dados_existentes["data_hora"])
        # Importante: sem isso, codigos com zero a esquerda (ex: "02042051")
        # voltam do CSV como numero e perdem o zero (viram 2042051).
        dados_existentes["codigo_estacao"] = (
            dados_existentes["codigo_estacao"].astype(str).str.zfill(8)
        )
        data_inicio = dados_existentes["data_hora"].max()
    else:
        data_inicio = DATA_INICIO_PADRAO

    dados_novos = ingestao_ana.baixar_estacao(codigo, data_inicio=data_inicio, verbose=False)

    if dados_novos.empty and carga_inicial:
        return {"situacao": "sem_dados", "carga_inicial": True}

    if carga_inicial:
        consolidado = dados_novos
    else:
        consolidado = pd.concat([dados_existentes, dados_novos], ignore_index=True)

    consolidado = consolidado.drop_duplicates(
        subset=["codigo_estacao", "data_hora"], keep="last"
    )
    consolidado = consolidado.sort_values("data_hora").reset_index(drop=True)

    drive_io.salvar_csv(servico, consolidado, nome_arquivo, config.PASTA_ESTACOES_ID)

    resultado = {
        "situacao": "sucesso",
        "registros_novos": len(dados_novos),
        "registros_totais": len(consolidado),
        "carga_inicial": carga_inicial,
    }

    if carga_inicial and not dados_novos.empty:
        resultado["data_inicio_detectada"] = dados_novos["data_hora"].min()

    return resultado


def rodar_pipeline(caminho_chave_json, inicio=0, limite=None):
    """Roda o pipeline completo: loop pela lista de estacoes, com isolamento de
    falhas, gerando os logs de erro e de carga inicial ao final.

    Parametros
    ----------
    caminho_chave_json : str
        Caminho local da chave da conta de servico.
    inicio : int
        Indice (a partir de 0) de onde comecar na lista de estacoes -- use isso
        para rodar em lotes (ex: inicio=20 comeca da 21a estacao da lista).
    limite : int, opcional
        Quantas estacoes processar a partir de "inicio". Se omitido, processa
        ate o final da lista.
    """
    servico = drive_io.conectar_drive(caminho_chave_json)
    codigos = carregar_lista_estacoes(servico)

    if limite is not None:
        codigos = codigos[inicio : inicio + limite]
    else:
        codigos = codigos[inicio:]

    data_execucao = datetime.now(FUSO_BRASIL)
    erros = []
    cargas_iniciais = []

    for indice, codigo in enumerate(codigos, start=1):
        print(f"[{indice}/{len(codigos)}] Estacao {codigo}")
        try:
            resultado = processar_estacao(servico, codigo)
            print(f"  {resultado}")

            if resultado["situacao"] == "sem_dados":
                erros.append(
                    {
                        "data_execucao": data_execucao,
                        "codigo_estacao": codigo,
                        "situacao": "Sem dados retornados pela API",
                    }
                )
            elif resultado.get("carga_inicial") and "data_inicio_detectada" in resultado:
                data_detectada = resultado["data_inicio_detectada"]
                if data_detectada > pd.Timestamp("2014-01-01"):
                    cargas_iniciais.append(
                        {
                            "data_execucao": data_execucao,
                            "codigo_estacao": codigo,
                            "data_inicio_detectada": data_detectada,
                        }
                    )

        except Exception as erro:  # noqa: BLE001 -- isolamento de falhas por estacao
            print(f"  ERRO: {erro}")
            erros.append(
                {
                    "data_execucao": data_execucao,
                    "codigo_estacao": codigo,
                    "situacao": f"{type(erro).__name__}: {erro}",
                }
            )

    if erros:
        drive_io.acrescentar_linhas(
            servico, pd.DataFrame(erros), "log_erros.csv", config.PASTA_RELATORIOS_ID
        )
    if cargas_iniciais:
        drive_io.acrescentar_linhas(
            servico,
            pd.DataFrame(cargas_iniciais),
            "log_cargas_iniciais.csv",
            config.PASTA_RELATORIOS_ID,
        )

    print(f"\nExecucao concluida: {len(codigos)} estacoes, {len(erros)} erro(s)/pendencia(s).")