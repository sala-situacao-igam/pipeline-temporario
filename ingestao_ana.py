"""
Descrição: consulta a API da ANA para uma estação por vez e devolve os
dados tratados e tipados. Não sabe nada sobre a lista de estações, o
Google Drive ou o loop diário -- essas responsabilidades ficam no
orquestrador (Fase 2).

Conexões do Pipeline:
- Entradas: nenhuma dependência de outro módulo do projeto (consome diretamente a API da ANA).
- Saídas: consumido por orquestrador.py (processar_estacao).

Funções:
- normalizar_data: converte uma data para o formato dd/mm/aaaa exigido pela API.
- variacoes_codigo: gera variações do código da estação (com/sem zero à esquerda).
- consultar_ana: faz uma única chamada bruta à API para um código e intervalo de datas.
- baixar_estacao: orquestra a consulta (com fallback de código) e devolve o DataFrame limpo e tipado.
"""

import re
from datetime import date, datetime

import pandas as pd
import requests
from lxml import etree

URL_ANA = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos"


def normalizar_data(valor):
    """Converte uma data (str em dd/mm/aaaa ou aaaa-mm-dd, ou objeto date/datetime)
    para o formato dd/mm/aaaa exigido pela API da ANA."""
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")

    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(valor).strip(), formato).strftime("%d/%m/%Y")
        except ValueError:
            pass

    raise ValueError(f"Data invalida: {valor!r}")


def variacoes_codigo(codigo):
    """Gera variacoes plausiveis do codigo da estacao (com e sem zero a esquerda),
    porque a API da ANA as vezes so reconhece uma das duas formas."""
    codigo = re.sub(r"\D", "", str(codigo))
    if not codigo:
        raise ValueError("O codigo da estacao nao pode estar vazio")

    codigos = [codigo]
    if codigo.startswith("0"):
        sem_zero = codigo.lstrip("0")
        if sem_zero:
            codigos.append(sem_zero)
    elif len(codigo) < 8:
        codigos.append(codigo.zfill(8))

    return list(dict.fromkeys(codigos))


def consultar_ana(codigo, data_inicio, data_fim):
    """Faz uma unica chamada a API da ANA para um codigo de estacao e intervalo de datas.

    Retorna uma tupla (registros, erros), ambos ainda brutos (sem tratamento/tipagem).
    """
    parametros = {
        "codEstacao": codigo,
        "dataInicio": data_inicio,
        "dataFim": data_fim,
    }
    registros = []
    erros = []

    with requests.get(URL_ANA, params=parametros, stream=True, timeout=(30, 600)) as resposta:
        resposta.raise_for_status()
        resposta.raw.decode_content = True

        for _, elemento in etree.iterparse(resposta.raw, events=("end",), recover=True):
            nome = etree.QName(elemento).localname

            if nome == "DadosHidrometereologicos":
                registro = {
                    etree.QName(campo).localname: campo.text.strip() if campo.text else None
                    for campo in elemento
                }
                registros.append(registro)

                elemento.clear()
                pai = elemento.getparent()
                if pai is not None:
                    while elemento.getprevious() is not None:
                        del pai[0]

            elif nome == "Error" and elemento.text:
                erros.append(elemento.text.strip())

    return registros, erros


def baixar_estacao(codigo, data_inicio, data_fim=None, verbose=True):
    """Consulta a API da ANA para uma estacao (tentando variacoes do codigo, se
    necessario) e devolve um DataFrame limpo e tipado, pronto para ser tratado
    (Fase 3) ou salvo.

    Parametros
    ----------
    codigo : str
        Codigo da estacao (com ou sem zero a esquerda).
    data_inicio : str, date ou datetime
        Inicio do intervalo de consulta.
    data_fim : str, date ou datetime, opcional
        Fim do intervalo de consulta. Se omitido, usa a data de hoje.
    verbose : bool
        Se True, imprime mensagens de progresso (util ao rodar manualmente no Colab).

    Retorna
    -------
    pd.DataFrame com as colunas:
        codigo_estacao : string, codigo de 8 digitos
        data_hora      : datetime64
        chuva          : float (mm)
        nivel          : float (cm)
        vazao          : float (m3/s)
    """
    if data_fim is None:
        data_fim = date.today()

    inicio = normalizar_data(data_inicio)
    fim = normalizar_data(data_fim)
    registros = []

    for codigo_api in variacoes_codigo(codigo):
        if verbose:
            print(f"  Consultando codigo {codigo_api}...")

        registros, erros = consultar_ana(codigo_api, inicio, fim)
        for erro in erros:
            if verbose:
                print(f"  Aviso da ANA: {erro}")

        if registros:
            if verbose:
                print(f"  Dados encontrados com o codigo {codigo_api}: {len(registros):,} registros")
            break

        if verbose:
            print(f"  Nenhum dado encontrado com o codigo {codigo_api}")

    dados = pd.DataFrame(registros)
    if dados.empty:
        return pd.DataFrame(columns=["codigo_estacao", "data_hora", "chuva", "nivel", "vazao"])

    codigo_padronizado = re.sub(r"\D", "", str(codigo)).zfill(8)
    dados["codigo_estacao"] = codigo_padronizado

    if "DataHora" in dados.columns:
        dados["data_hora"] = pd.to_datetime(
            dados["DataHora"].astype("string").str.strip(), errors="coerce"
        )
    else:
        dados["data_hora"] = pd.NaT

    # Tipagem numerica estrita -- Chuva, Nivel e Vazao (antes, so Chuva era convertida)
    mapa_colunas_origem = {"chuva": "Chuva", "nivel": "Nivel", "vazao": "Vazao"}
    for coluna_final, coluna_origem in mapa_colunas_origem.items():
        if coluna_origem in dados.columns:
            dados[coluna_final] = pd.to_numeric(
                dados[coluna_origem].astype("string").str.replace(",", ".", regex=False),
                errors="coerce",
            )
        else:
            dados[coluna_final] = pd.NA

    return dados[["codigo_estacao", "data_hora", "chuva", "nivel", "vazao"]]