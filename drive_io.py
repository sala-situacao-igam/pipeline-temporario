"""
Descrição: camada de acesso ao Google Drive (Drive Compartilhado) via conta
de serviço -- autenticação, leitura/escrita de CSV, Parquet, Planilha
Google e arquivos genéricos. 
Todas as chamadas usam supportsAllDrives=True, porque as pastas do projeto vivem num Drive Compartilhado; 
chamadas de rede usam NUM_RETRIES para tolerar erros transitórios (ex.: rate limit).

Conexões do Pipeline:
- Entradas: chave de serviço (.json); nenhuma dependência de outro módulo do projeto.
- Saídas: usado por orquestrador.py, pipeline_consistencia.py,
  indicador_2_2_calculo.py, extrair_documentos_simge_calculo.py,
  rodar_diario_hidro.py, rodar_diario_meteoro.py, gerar_relatorios_visuais.py.

Funções:
- conectar_drive: autentica com a conta de serviço e devolve o cliente da API do Drive.
- buscar_arquivo_id: localiza o ID de um arquivo pelo nome dentro de uma pasta.
- ler_csv: lê um CSV do Drive e devolve um DataFrame.
- salvar_csv: cria ou sobrescreve um CSV no Drive a partir de um DataFrame.
- salvar_planilha_google: salva um DataFrame como Planilha Google nativa (fonte do Looker Studio).
- ler_parquet: lê um Parquet do Drive e devolve um DataFrame.
- salvar_parquet: cria ou sobrescreve um Parquet no Drive a partir de um DataFrame.
- salvar_arquivo: envia ao Drive um arquivo já existente em disco (PNG, HTML, etc.).
- acrescentar_linhas: lê o CSV existente, acrescenta linhas novas e salva de volta (uso cumulativo).
- listar_arquivos: lista todos os arquivos de uma pasta do Drive.
"""

import io
import mimetypes

import pandas as pd
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

SCOPES = ["https://www.googleapis.com/auth/drive"]

# Numero de tentativas automaticas em caso de erro transitorio (rate limit,
# instabilidade momentanea, etc.) antes de desistir e propagar o erro.
NUM_RETRIES = 5


def conectar_drive(caminho_chave_json):
    """Autentica com a conta de servico e devolve um cliente da API do Drive."""
    credenciais = service_account.Credentials.from_service_account_file(
        caminho_chave_json, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credenciais)


def buscar_arquivo_id(servico, nome_arquivo, pasta_id):
    """Procura um arquivo pelo nome dentro de uma pasta especifica do Drive
    (incluindo Drives Compartilhados).
    Devolve o ID do arquivo, ou None se ele ainda nao existir.
    """
    query = (
        f"name = '{nome_arquivo}' and '{pasta_id}' in parents and trashed = false"
    )
    resultado = (
        servico.files()
        .list(
            q=query,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            corpora="allDrives",
        )
        .execute(num_retries=NUM_RETRIES)
    )
    arquivos = resultado.get("files", [])
    return arquivos[0]["id"] if arquivos else None


def ler_csv(servico, nome_arquivo, pasta_id, sep=","):
    """Le um CSV do Drive e devolve um DataFrame.
    Se o arquivo ainda nao existir na pasta, devolve None (quem chama decide o
    que fazer nesse caso -- por exemplo, tratar como "carga inicial").
    Use sep=";" para arquivos como o frente1.csv, que vem nesse formato.
    """
    arquivo_id = buscar_arquivo_id(servico, nome_arquivo, pasta_id)
    if arquivo_id is None:
        return None

    request = servico.files().get_media(fileId=arquivo_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    concluido = False
    while not concluido:
        _, concluido = downloader.next_chunk(num_retries=NUM_RETRIES)

    buffer.seek(0)
    return pd.read_csv(buffer, sep=sep)


def salvar_csv(servico, df, nome_arquivo, pasta_id):
    """Salva um DataFrame como CSV no Drive -- cria o arquivo se nao existir,
    ou sobrescreve o conteudo se ja existir (mesmo ID, mesmo arquivo)."""
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False, encoding="utf-8-sig")
    buffer.seek(0)

    media = MediaIoBaseUpload(buffer, mimetype="text/csv", resumable=True)
    arquivo_id = buscar_arquivo_id(servico, nome_arquivo, pasta_id)

    if arquivo_id is None:
        metadados = {"name": nome_arquivo, "parents": [pasta_id]}
        servico.files().create(
            body=metadados, media_body=media, fields="id", supportsAllDrives=True
        ).execute(num_retries=NUM_RETRIES)
    else:
        servico.files().update(
            fileId=arquivo_id, media_body=media, supportsAllDrives=True
        ).execute(num_retries=NUM_RETRIES)

def salvar_planilha_google(servico, df, nome_arquivo, pasta_id):
    """Salva um DataFrame como Planilha Google nativa -- usado
    para as fontes que alimentam o Data Studio, que só atualiza sozinho
    quando o conteúdo é uma Planilha nativa

    Manda os mesmos bytes de CSV (via MediaIoBaseUpload), mas na criação
    do arquivo pede pro Drive converter automaticamente para
    "application/vnd.google-apps.spreadsheet"; nas chamadas seguintes só
    reenvia o conteúdo (update) e o Drive converte de novo, pois o destino
    já é nativo. Mesmo ID, mesmo arquivo entre uma chamada e outra -- igual
    salvar_csv(). Não mexe no arquivo .csv equivalente: use um nome
    diferente (sem ".csv" no final) para não confundir as duas versões na
    pasta do Drive.

    DESLIGADA (14/09) -- a conversão CSV->Planilha Google estava dando
    timeout com o fato_disponibilidade.csv grande, derrubando a rodada
    inteira antes da Fase 5. Não está mais em uso -- a função continua
    existindo (em vez de apagada) só pra não quebrar as duas chamadas que
    já existem em pipeline_consistencia.py. Se um dia precisar religar, é
    só remover o "return" abaixo e descomentar o corpo original.
    """
    print(f"  (Planilha Google '{nome_arquivo}' desligada -- pulando.)")
    return

    # -- corpo original, desligado --
    # buffer = io.BytesIO()
    # df.to_csv(buffer, index=False, encoding="utf-8-sig")
    # buffer.seek(0)
    #
    # media = MediaIoBaseUpload(buffer, mimetype="text/csv", resumable=True)
    # arquivo_id = buscar_arquivo_id(servico, nome_arquivo, pasta_id)
    #
    # if arquivo_id is None:
    #     metadados = {
    #         "name": nome_arquivo,
    #         "parents": [pasta_id],
    #         "mimeType": "application/vnd.google-apps.spreadsheet",
    #     }
    #     servico.files().create(
    #         body=metadados, media_body=media, fields="id", supportsAllDrives=True
    #     ).execute(num_retries=NUM_RETRIES)
    # else:
    #     servico.files().update(
    #         fileId=arquivo_id, media_body=media, supportsAllDrives=True
    #     ).execute(num_retries=NUM_RETRIES)

def ler_parquet(servico, nome_arquivo, pasta_id):
    """Le um Parquet do Drive e devolve um DataFrame. Se o arquivo ainda nao
    existir, devolve None."""
    arquivo_id = buscar_arquivo_id(servico, nome_arquivo, pasta_id)
    if arquivo_id is None:
        return None

    request = servico.files().get_media(fileId=arquivo_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    concluido = False
    while not concluido:
        _, concluido = downloader.next_chunk(num_retries=NUM_RETRIES)

    buffer.seek(0)
    return pd.read_parquet(buffer)


def salvar_parquet(servico, df, nome_arquivo, pasta_id):
    """Salva um DataFrame como Parquet no Drive -- cria ou sobrescreve.
    Usado para o detalhe por medicao (flags linha a linha), mais compacto e
    com tipos preservados melhor que CSV."""
    buffer = io.BytesIO()
    df.to_parquet(buffer, index=False)
    buffer.seek(0)

    media = MediaIoBaseUpload(buffer, mimetype="application/octet-stream", resumable=True)
    arquivo_id = buscar_arquivo_id(servico, nome_arquivo, pasta_id)

    if arquivo_id is None:
        metadados = {"name": nome_arquivo, "parents": [pasta_id]}
        servico.files().create(
            body=metadados, media_body=media, fields="id", supportsAllDrives=True
        ).execute(num_retries=NUM_RETRIES)
    else:
        servico.files().update(
            fileId=arquivo_id, media_body=media, supportsAllDrives=True
        ).execute(num_retries=NUM_RETRIES)


def salvar_arquivo(servico, caminho_local, nome_arquivo, pasta_id):
    """Envia ao Drive um arquivo que já existe no disco (PNG, HTML, etc.) --
    cria se não existir, ou sobrescreve o conteúdo se já existir (mesmo ID,
    mesmo arquivo). Diferente das outras funções salvar_*, que recebem um
    DataFrame em memória e o convertem (CSV/Parquet), esta lê um arquivo
    pronto do disco, servindo para qualquer tipo -- imagem, HTML, PDF, etc.

    `caminho_local`: onde o arquivo está salvo localmente. `nome_arquivo`:
    nome com que deve ficar salvo no Drive. O mimetype é descoberto
    automaticamente pela extensão; se não reconhecida, usa um tipo
    genérico.
    """
    mimetype, _ = mimetypes.guess_type(caminho_local)
    if mimetype is None:
        mimetype = "application/octet-stream"

    media = MediaFileUpload(caminho_local, mimetype=mimetype, resumable=True)
    arquivo_id = buscar_arquivo_id(servico, nome_arquivo, pasta_id)

    if arquivo_id is None:
        metadados = {"name": nome_arquivo, "parents": [pasta_id]}
        servico.files().create(
            body=metadados, media_body=media, fields="id", supportsAllDrives=True
        ).execute(num_retries=NUM_RETRIES)
    else:
        servico.files().update(
            fileId=arquivo_id, media_body=media, supportsAllDrives=True
        ).execute(num_retries=NUM_RETRIES)

    print(f"Arquivo salvo no Drive: {nome_arquivo}")


def acrescentar_linhas(servico, df_novo, nome_arquivo, pasta_id):
    """Le o CSV existente (se houver), acrescenta as novas linhas ao final e
    salva de volta. E o padrao usado pelos relatorios cumulativos (indicadores
    diarios, log de erros, log de cargas iniciais) -- nunca sobrescreve o
    historico, so cresce."""
    df_existente = ler_csv(servico, nome_arquivo, pasta_id)
    if df_existente is not None:
        df_final = pd.concat([df_existente, df_novo], ignore_index=True)
    else:
        df_final = df_novo

    salvar_csv(servico, df_final, nome_arquivo, pasta_id)
    return df_final


def listar_arquivos(servico, pasta_id):
    """Lista TODOS os arquivos dentro de uma pasta do Drive com nome, id, tamanho e data de modificacao.
    """
    arquivos = []
    token_pagina = None
    while True:
        resultado = (
            servico.files()
            .list(
                q=f"'{pasta_id}' in parents and trashed = false",
                fields="nextPageToken, files(id, name, size, modifiedTime)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
                corpora="allDrives",
                pageSize=1000,
                pageToken=token_pagina,
            )
            .execute(num_retries=NUM_RETRIES)
        )
        arquivos.extend(resultado.get("files", []))
        token_pagina = resultado.get("nextPageToken")
        if not token_pagina:
            break
    return arquivos
