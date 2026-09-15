"""
Descrição: Passo 1 (Frente 2.1) do pipeline -- captura incremental diária
das estações da Frente 1 a partir da API NOVA da ANA (rota Detalhada),
com isolamento de falhas por estação. Espelha orquestrador.py (API antiga),
mas é um módulo separado de propósito: as duas capturas não se substituem
-- a antiga alimenta o histórico completo (2.2), a nova é só janela rolante
de ~30 dias, complementar, usada pelo indicador 2.1.

Conexões do Pipeline:
- Entradas: frente1.csv (Drive, config.PASTA_DATA_ID) -- reaproveita
  orquestrador.carregar_lista_estacoes(); histórico existente em
  config.PASTA_TELEMETRIA_DETALHADA_ID; usa ingestao_ana_nova.py e
  drive_io.py.
- Saídas: estacao_detalhada_XXXXXXXX.csv por estação
  (config.PASTA_TELEMETRIA_DETALHADA_ID),
  log_erros_telemetria_detalhada.csv (config.PASTA_RELATORIOS_ID -- log
  PRÓPRIO, separado do log_erros.csv da API antiga, pra não misturar
  falhas de sistemas diferentes no mesmo relatório). Chamado por
  rodar_diario_hidro.py.

Funções:
- processar_estacao_detalhada: busca os dados novos de uma estação, funde
  com o histórico e salva no Drive (mesma lógica que já foi testada no
  Colab, só reorganizada em módulo).
- rodar_pipeline_detalhada: roda processar_estacao_detalhada para todas as
  estações (ou um lote), com isolamento de falhas, reautenticação
  automática do token e log de erros dedicado.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config
import drive_io
import ingestao_ana_nova
import orquestrador  # reaproveita carregar_lista_estacoes (mesmo frente1.csv)

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")
NOME_LOG_ERROS_DETALHADA = "log_erros_telemetria_detalhada.csv"


def processar_estacao_detalhada(servico, codigo, token, pasta_id):
    """Processa uma única estação: busca os itens novos na API nova, funde
    com o histórico existente no Drive, deduplica e salva de volta.

    O nome do arquivo sempre usa codigo.zfill(8) (padrão do projeto).
    Devolve um dicionário com o resultado (usado pelo orquestrador pra
    decidir o que registrar no log).
    """
    codigo_padronizado = str(codigo).zfill(8)
    nome_arquivo = f"estacao_detalhada_{codigo_padronizado}.csv"

    itens_novos = ingestao_ana_nova.buscar_pacotes_estacao(codigo_padronizado, token)
    df_novos = pd.DataFrame(itens_novos)

    if df_novos.empty:
        # Não é erro -- é estação muda (já sabemos que 20 das 64 estão
        # assim). Não sobrescreve nem cria arquivo -- é assim que o
        # relatório fato_ultima_atualizacao_estacao.csv consegue usar "tem
        # arquivo na pasta" como sinal de "tem dado no período".
        return {"situacao": "sem_dados_novos", "registros_novos": 0}

    df_existente = drive_io.ler_csv(servico, nome_arquivo, pasta_id)
    if df_existente is not None and not df_existente.empty:
        df_final = pd.concat([df_existente, df_novos], ignore_index=True)
    else:
        df_final = df_novos

    # Padroniza o tipo do código da estação -- sem isso, "60927010" (vindo
    # da API) e 60927010 (relido do CSV como número) são tratados como
    # valores diferentes e o dedup não funciona.
    df_final["codigoestacao"] = df_final["codigoestacao"].astype(str).str.zfill(8)

    # Remove qualquer fração de segundo antes de converter, com formato
    # fixo e único -- sem inferência/adivinhação de formato.
    datas_limpas = df_final["Data_Hora_Medicao"].astype(str).str.replace(r"\.\d+$", "", regex=True)
    df_final["Data_Hora_Medicao"] = pd.to_datetime(datas_limpas, format="%Y-%m-%d %H:%M:%S")

    total_antes = len(df_final)
    df_final = df_final.drop_duplicates(subset=["codigoestacao", "Data_Hora_Medicao"], keep="last")
    df_final = df_final.sort_values("Data_Hora_Medicao").reset_index(drop=True)

    drive_io.salvar_csv(servico, df_final, nome_arquivo, pasta_id)

    return {
        "situacao": "sucesso",
        "registros_novos": len(df_novos),
        "duplicatas_removidas": total_antes - len(df_final),
        "registros_totais": len(df_final),
    }


def rodar_pipeline_detalhada(caminho_chave_json, identificador, senha, estacoes=None,
                              inicio=0, limite=None):
    """Roda a captura incremental da API nova pra todas as estações da
    Frente 1 (ou uma lista/lote específico), com isolamento de falhas,
    reautenticação automática do token quando ele estiver perto de expirar,
    e log de erros dedicado.

    Parâmetros
    ----------
    caminho_chave_json : str
        Caminho local da chave da conta de serviço (mesma de sempre).
    identificador, senha : str
        Credenciais da API nova -- em produção, vêm de
        ingestao_ana_nova.ler_credenciais_ambiente() (Secrets do Actions);
        em teste manual, de ingestao_ana_nova.pedir_credenciais_interativo().
        Nunca hardcode aqui.
    estacoes : list, opcional
        Lista de códigos a processar. Se omitido, usa a mesma lista de
        orquestrador.carregar_lista_estacoes() (frente1.csv).
    inicio, limite : int, opcional
        Pra rodar em lotes, igual orquestrador.rodar_pipeline().

    Devolve (servico, resumo) -- `servico` já conectado, pra reaproveitar
    em seguida (cálculo de CD, fato_ultima_atualizacao_estacao) sem
    reconectar no Drive.
    """
    servico = drive_io.conectar_drive(caminho_chave_json)

    if estacoes is None:
        estacoes = orquestrador.carregar_lista_estacoes(servico)

    if limite is not None:
        estacoes = estacoes[inicio: inicio + limite]
    else:
        estacoes = estacoes[inicio:]

    token, token_gerado_em = ingestao_ana_nova.autenticar(identificador, senha)

    data_execucao = datetime.now(FUSO_BRASIL)
    erros = []
    resumo = []

    for indice, codigo in enumerate(estacoes, start=1):
        if ingestao_ana_nova.token_expirado(token_gerado_em):
            print("  Token perto de expirar -- reautenticando...")
            token, token_gerado_em = ingestao_ana_nova.autenticar(identificador, senha)

        print(f"[{indice}/{len(estacoes)}] Estação {codigo}")
        try:
            resultado = processar_estacao_detalhada(
                servico, codigo, token, config.PASTA_TELEMETRIA_DETALHADA_ID
            )
            print(f"  {resultado}")
            resumo.append({"codigo_estacao": str(codigo).zfill(8), **resultado})

            if resultado["situacao"] == "sem_dados_novos":
                erros.append({
                    "data_execucao": data_execucao,
                    "codigo_estacao": codigo,
                    "situacao": "Sem dados novos retornados pela API nova",
                })

        except Exception as erro:  # noqa: BLE001 -- isolamento de falhas por estacao
            print(f"  ERRO: {erro}")
            erros.append({
                "data_execucao": data_execucao,
                "codigo_estacao": codigo,
                "situacao": f"{type(erro).__name__}: {erro}",
            })

    if erros:
        drive_io.acrescentar_linhas(
            servico, pd.DataFrame(erros), NOME_LOG_ERROS_DETALHADA, config.PASTA_RELATORIOS_ID
        )

    print(f"\nExecução concluída: {len(estacoes)} estações, {len(erros)} erro(s)/pendência(s).")
    return servico, resumo
