"""
Descrição: consulta a API NOVA da ANA (HidroWebService, rota Detalhada) para
uma estação por vez e devolve os itens brutos. Não sabe nada sobre a lista
de estações, o Google Drive ou o loop diário -- essas responsabilidades
ficam no orquestrador_telemetria_detalhada (Fase 2). Mesma separação de
responsabilidades que ingestao_ana.py já usa pra API antiga -- essa API
antiga continua intocada, essa é uma captura paralela e complementar,
usada só pelo indicador 2.1 (janela rolante de ~30 dias, sem histórico
profundo).

Conexões do Pipeline:
- Entradas: nenhuma dependência de outro módulo do projeto (consome
  diretamente a API nova da ANA). Precisa de ANA_IDENTIFICADOR e ANA_SENHA
  (Secrets do GitHub Actions em produção; digitados via getpass em teste
  manual -- nunca hardcoded).
- Saídas: consumido por orquestrador_telemetria_detalhada.py (processar_estacao_detalhada).

Funções:
- autenticar: pega o token de autenticação (válido por ~60 min).
- token_expirado: confere se um token já passou da validade (com folga de segurança).
- buscar_pacotes_estacao: busca os itens dos últimos ~30 dias de uma estação.
- ler_credenciais_ambiente: lê ANA_IDENTIFICADOR/ANA_SENHA das variáveis de
  ambiente (uso em produção, GitHub Actions).
- pedir_credenciais_interativo: pede as credenciais digitadas (getpass) --
  uso em teste manual no Colab, nunca fica salvo em nenhum arquivo.
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests

URL_OAUTH = "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas/OAUth/v1"
URL_DETALHADA = "https://www.ana.gov.br/hidrowebservice/EstacoesTelemetricas/HidroinfoanaSerieTelemetricaDetalhada/v1"

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")

# Validade real do token é 60 min -- reautentica um pouco antes disso pra
# ter folga de segurança e não arriscar um 401 no meio de um lote.
VALIDADE_TOKEN_MINUTOS = 55


def autenticar(identificador, senha):
    """Autentica na API nova e devolve (token, gerado_em). `gerado_em` é o
    horário local (fuso Brasil) em que o token foi obtido -- use junto com
    token_expirado() pra decidir quando reautenticar num loop longo."""
    resposta = requests.get(
        URL_OAUTH,
        headers={"Identificador": identificador, "Senha": senha},
        timeout=30,
    )
    resposta.raise_for_status()
    dados = resposta.json()

    # A chave exata pode vir no topo ou dentro de "items", dependendo da
    # versão da API -- cobre os dois formatos.
    if "tokenautenticacao" in dados:
        token = dados["tokenautenticacao"]
    else:
        token = dados["items"]["tokenautenticacao"]

    return token, datetime.now(FUSO_BRASIL)


def token_expirado(gerado_em):
    """True se o token já passou de VALIDADE_TOKEN_MINUTOS desde que foi gerado."""
    idade = datetime.now(FUSO_BRASIL) - gerado_em
    return idade > timedelta(minutes=VALIDADE_TOKEN_MINUTOS)


def buscar_pacotes_estacao(codigo_estacao, token, data_referencia=None):
    """Busca os itens brutos (ainda sem tratamento) dos últimos ~30 dias de
    uma estação na rota Detalhada. `data_referencia` no formato yyyy-MM-dd;
    se omitido, usa hoje (a API ignora datas de busca mais antigas -- só
    entrega a janela rolante a partir de hoje, isso já foi confirmado por
    teste real e não dá pra contornar).

    Devolve uma lista de dicionários (podem vir vazios se a estação não tem
    dado novo no período -- isso não é erro, é estação muda)."""
    if data_referencia is None:
        data_referencia = datetime.now(FUSO_BRASIL).strftime("%Y-%m-%d")

    params = {
        "Código da Estação": codigo_estacao,
        "Tipo Filtro Data": "DATA_LEITURA",
        "Data de Busca": data_referencia,
        "Range Intervalo de busca": "DIAS_30",
    }
    headers = {"Authorization": f"Bearer {token}"}

    resposta = requests.get(URL_DETALHADA, headers=headers, params=params, timeout=45)
    if resposta.status_code == 401:
        raise PermissionError("Token expirado (401) -- reautentique antes de tentar de novo.")
    resposta.raise_for_status()

    return resposta.json().get("items", [])


def ler_credenciais_ambiente():
    """Lê ANA_IDENTIFICADOR/ANA_SENHA das variáveis de ambiente -- é assim
    que o GitHub Actions passa os Secrets pro script (ver env: no .yml).
    Levanta erro claro se alguma faltar, em vez de deixar autenticar()
    falhar com uma mensagem confusa."""
    identificador = os.environ.get("ANA_IDENTIFICADOR")
    senha = os.environ.get("ANA_SENHA")
    if not identificador or not senha:
        raise EnvironmentError(
            "ANA_IDENTIFICADOR e/ou ANA_SENHA não encontrados nas variáveis de "
            "ambiente. Em produção, confira os Secrets do GitHub Actions e o "
            "env: do workflow; em teste manual, use pedir_credenciais_interativo()."
        )
    return identificador, senha


def pedir_credenciais_interativo():
    """Pede as credenciais digitadas na hora (getpass) -- só pra teste manual
    no Colab. Nunca fica salvo em nenhuma célula/arquivo, some da memória
    quando a sessão acaba."""
    import getpass
    identificador = getpass.getpass("Identificador (CPF/CNPJ) da API nova da ANA: ")
    senha = getpass.getpass("Senha: ")
    return identificador, senha
