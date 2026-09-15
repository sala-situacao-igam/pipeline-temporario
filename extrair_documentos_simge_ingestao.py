"""
Descrição: extrai a lista de documentos/alertas publicados no site do
SIMGE (previsões -- 4.1, tendência climática -- 4.3, alertas de
tempestade severa -- 4.2) dentro de um período.

Conexões do Pipeline:
- Entradas: páginas públicas do SIMGE (simge.mg.gov.br), via requests.
- Saídas: usado por extrair_documentos_simge_calculo.py.

Funções:
- buscar_pagina: busca uma página do repositório de documentos (previsões/tendência climática).
- extrair_linhas: extrai (data_criação, título) de cada documento de uma página.
- _coletar_periodo: pagina e filtra os documentos dentro de um período.
- _buscar_pagina_alertas: busca uma página da lista de alertas de tempestade severa.
- _parse_data_alerta_pt: converte a data por extenso do alerta em um objeto date.
- _extrair_blocos_alertas: extrai os blocos de alerta (um por dia) de uma página.
- coletar_alertas_periodo: navega as páginas de alertas e devolve os dias dentro de um período.

As duas páginas de documentos (previsões e tendência climática) usam um
portlet de biblioteca de documentos do Liferay; uma única chamada com
`deltaEntry` alto já traz o ano inteiro. A página de alertas usa um
portlet diferente (Asset Publisher, instância "lwcy") que não responde a
um delta alto, por isso `coletar_alertas_periodo` navega página por
página até passar de `data_inicio` ou a página vir vazia.

Uso colab:
    from extrair_documentos_simge_ingestao import (
        URL_PASTA_PREVISOES_2026,
        URL_PASTA_TENDENCIA_CLIMATICA_2026,
        URL_ALERTAS_TEMPESTADE_SEVERA,
    )
    from extrair_documentos_simge_calculo import (
        contar_previsoes_4_1,
        contar_tendencia_climatica_4_3,
        contar_alertas_4_2,
    )

    resultado_4_1 = contar_previsoes_4_1(URL_PASTA_PREVISOES_2026, "2026-01-01", "2026-08-31")
    resultado_4_3 = contar_tendencia_climatica_4_3(URL_PASTA_TENDENCIA_CLIMATICA_2026, "2026-01-01", "2026-08-31")
    resultado_4_2 = contar_alertas_4_2(URL_ALERTAS_TEMPESTADE_SEVERA, "2026-01-01", "2026-08-31")
"""
import re
import time
from datetime import date, datetime

import requests

HEADERS = {"User-Agent": "Mozilla/5.0 (compativel; indicadores IGAM/APPA)"}

# Nome da pasta/instancia do portlet -- fixos, confirmados em 28-31/08.
INSTANCIA_PREVISOES = "nrvm"        # indicador 4.1
INSTANCIA_TENDENCIA = "tcwg"        # indicador 4.3

# URLs das pastas 2026
URL_PASTA_PREVISOES_2026 = (
    "https://simge.mg.gov.br/previs%C3%B5es/-/document_library/nrvm/view/9814139"
    "?_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_nrvm_folderId=9814139"
)
URL_PASTA_TENDENCIA_CLIMATICA_2026 = (
    "https://simge.mg.gov.br/tendencia-climatica/-/document_library/tcwg/view/9867148"
    "?_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_tcwg_folderId=9867148"
)

# Indicador 4.2 -- página de alertas (não tem "pasta"/ano na URL, é uma
# única listagem contínua, mais antiga primeiro tem que navegar bastante).
INSTANCIA_ALERTAS = "lwcy"
URL_ALERTAS_TEMPESTADE_SEVERA = "https://simge.mg.gov.br/alerta-de-tempestade-severa"

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

# Cada bloco de documento no HTML do Liferay comeca com este marcador.
MARCADOR_LINHA = re.compile(r'data-qa-id="row"')

# Dentro de um bloco de linha: nome do arquivo (limpo, uma vez só).
PADRAO_TITULO = re.compile(r'data-title="([^"]+)"')

# Dentro de um bloco de linha: data/hora exata de criação (tooltip).
PADRAO_DATA_HORA = re.compile(
    r'class="lfr-portal-tooltip"[^>]*title="(\d{2}/\d{2}/\d{2} \d{2}:\d{2})"'
)

def buscar_pagina(url, instancia_portlet, pagina=1, itens_por_pagina=500):
    """Busca uma página do repositório de documentos.

    `instancia_portlet`: "nrvm" (Previsões, 4.1) ou "tcwg" (Tendência
    Climática, 4.3). Com itens_por_pagina alto (500) uma única chamada já
    traz o ano inteiro."""
    prefixo = f"_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_{instancia_portlet}"
    separador = "&" if "?" in url else "?"
    url_completa = (
        f"{url}{separador}"
        f"{prefixo}_navigation=home"
        f"&{prefixo}_orderByCol=modifiedDate"
        f"&{prefixo}_orderByType=desc"
        f"&{prefixo}_deltaEntry={itens_por_pagina}"
        f"&{prefixo}_curEntry={pagina}"
    )
    resposta = requests.get(url_completa, headers=HEADERS, timeout=30)
    resposta.raise_for_status()
    return resposta.text


def extrair_linhas(html):
    """Extrai (datetime_criacao, titulo) de cada documento, usando a
    estrutura real de linha do Liferay (data-qa-id="row") -- um titulo
    limpo por linha, sem duplicidade. Ignora qualquer bloco que não tenha
    os dois campos esperados"""
    encontrados = []
    vistos = set()
    blocos = MARCADOR_LINHA.split(html)[1:]  # descarta o que vem antes da 1ª linha
    for bloco in blocos:
        m_titulo = PADRAO_TITULO.search(bloco)
        m_data = PADRAO_DATA_HORA.search(bloco)
        if not m_titulo or not m_data:
            continue
        titulo = m_titulo.group(1)
        if titulo in vistos:
            continue
        try:
            dt_criacao = datetime.strptime(m_data.group(1), "%d/%m/%y %H:%M")
        except ValueError:
            continue
        vistos.add(titulo)
        encontrados.append((dt_criacao, titulo))
    return encontrados


def _coletar_periodo(url_pasta, instancia_portlet, data_inicio, data_fim, itens_por_pagina=500, max_paginas=5):
    """Busca todas as paginas necessarias e devolve as linhas (dt, titulo)
    cuja data de criacao cai dentro do periodo, ordenadas por data."""
    if isinstance(data_inicio, str):
        data_inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    if isinstance(data_fim, str):
        data_fim = datetime.strptime(data_fim, "%Y-%m-%d").date()

    todos = {}
    for pagina in range(1, max_paginas + 1):
        html = buscar_pagina(url_pasta, instancia_portlet, pagina=pagina, itens_por_pagina=itens_por_pagina)
        linhas_pagina = extrair_linhas(html)
        novos = [titulo for _, titulo in linhas_pagina if titulo not in todos]
        for dt_criacao, titulo in linhas_pagina:
            todos[titulo] = dt_criacao
        print(f"  Página {pagina}: {len(linhas_pagina)} linha(s) na resposta, {len(novos)} nova(s).")
        if not novos:
            if pagina == 1:
                print(
                    "  Nenhuma linha reconhecida na 1ª página -- confira a URL/instância "
                    "do portlet."
                )
            break

    no_periodo = [
        (dt_criacao, titulo)
        for titulo, dt_criacao in todos.items()
        if data_inicio <= dt_criacao.date() <= data_fim
    ]
    return sorted(no_periodo, key=lambda item: item[0])


# ---------------------------------------------------------------------
# Indicador 4.2 -- alertas de tempestade severa (portlet Asset Publisher,
# estrutura diferente das duas listas de documentos acima -- ver V2 no
# topo do arquivo). Adicionado 02/09/2026.
# ---------------------------------------------------------------------

def _buscar_pagina_alertas(url_alertas, pagina=1, delta=3):
    """Busca uma página da lista de alertas. `pagina` = número da página
    (parâmetro "_cur"), `delta` = itens (dias-com-alerta) por página
    (parâmetro "_delta") -- esta página não respeita um delta alto como as
    de documentos, então `coletar_alertas_periodo` sempre navega por
    página."""
    prefixo = f"_com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_{INSTANCIA_ALERTAS}"
    url = (
        f"{url_alertas}?p_p_id=com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_{INSTANCIA_ALERTAS}"
        f"&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        f"&{prefixo}_delta={delta}"
        f"&{prefixo}_cur={pagina}"
    )
    resposta = requests.get(url, headers=HEADERS, timeout=30)
    resposta.raise_for_status()
    return resposta.text


def _parse_data_alerta_pt(titulo):
    """'Terça-feira, 01 de setembro de 2026' -> date(2026, 9, 1). Tolera
    espaços extras entre a vírgula e o dia"""
    m = re.search(r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})', titulo)
    if not m:
        return None
    dia, mes_nome, ano = m.groups()
    mes = MESES_PT.get(mes_nome.lower())
    if not mes:
        return None
    try:
        return date(int(ano), mes, int(dia))
    except ValueError:
        return None


def _extrair_blocos_alertas(html):
    """Devolve uma lista de dicionários, um por dia com alerta(s)
    publicado(s) nessa página: {data (date), titulo, pk, alertas: [{hora,
    texto}, ...]}. Filtra automaticamente qualquer bloco cujo título não
    tenha uma data reconhecível (a página tem um bloco estático de
    introdução, sem data no título, que não é um dia da listagem de
    verdade)."""
    posicoes = [m.start() for m in re.finditer(r'class="asset-full-content', html)]
    posicoes.append(len(html))
    blocos = []
    for i in range(len(posicoes) - 1):
        trecho = html[posicoes[i]:posicoes[i + 1]]
        m_titulo = re.search(r'data-analytics-asset-title="([^"]+)"', trecho)
        m_pk = re.search(r'data-analytics-web-content-resource-pk="(\d+)"', trecho)
        if not m_titulo or not m_pk:
            continue
        titulo = m_titulo.group(1)
        data_alerta = _parse_data_alerta_pt(titulo)
        if not data_alerta:
            continue

        m_corpo = re.search(
            r'<div class="journal-content-article "[^>]*>(.*?)</div>\s*\n?\s*\n?\s*(?:</div>|$)',
            trecho, re.DOTALL,
        )
        corpo_html = m_corpo.group(1) if m_corpo else trecho
        texto_plano = re.sub(r'<[^>]+>', ' ', corpo_html)
        texto_plano = re.sub(r'&nbsp;', ' ', texto_plano)
        texto_plano = re.sub(r'\s+', ' ', texto_plano).strip()

        partes = re.split(r'(?=Alerta de Tempestade)', texto_plano)
        alertas = []
        for parte in partes:
            parte = parte.strip()
            if not parte.startswith("Alerta de Tempestade"):
                continue
            m_hora = re.search(r'às (\d{2}:\d{2})h', parte)
            alertas.append({"hora": m_hora.group(1) if m_hora else None, "texto": parte})

        blocos.append({"titulo": titulo, "pk": m_pk.group(1), "data": data_alerta, "alertas": alertas})
    return blocos


def coletar_alertas_periodo(url_alertas, data_inicio, data_fim, pausa_entre_paginas=0.5, max_paginas=200):
    """Coleta todos os dias-com-alerta dentro de [data_inicio, data_fim]
    (strings "AAAA-MM-DD" ou date). A lista vem do mais recente pro mais
    antigo -- navega página por página (3 dias por página) até passar da
    data_inicio ou a página vir vazia. Devolve lista de dicionários (ver
    `_extrair_blocos_alertas`), ordenada da mais antiga pra mais nova."""
    if isinstance(data_inicio, str):
        data_inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()
    if isinstance(data_fim, str):
        data_fim = datetime.strptime(data_fim, "%Y-%m-%d").date()

    vistos = {}  # pk -> bloco, pra nao duplicar

    html = _buscar_pagina_alertas(url_alertas, pagina=1, delta=500)
    for bloco in _extrair_blocos_alertas(html):
        vistos[bloco["pk"]] = bloco

    pagina = 2  # página 1 já coletada acima -- ver nota em coletar_alertas_periodo (V2)
    while pagina <= max_paginas:
        html = _buscar_pagina_alertas(url_alertas, pagina=pagina, delta=3)
        blocos_pagina = _extrair_blocos_alertas(html)
        if not blocos_pagina:
            break

        novos = 0
        for bloco in blocos_pagina:
            if bloco["pk"] not in vistos:
                vistos[bloco["pk"]] = bloco
                novos += 1

        mais_antiga = min(b["data"] for b in blocos_pagina)
        if novos == 0:
            break
        if mais_antiga < data_inicio:
            break

        pagina += 1
        time.sleep(pausa_entre_paginas)

    no_periodo = [b for b in vistos.values() if data_inicio <= b["data"] <= data_fim]
    return sorted(no_periodo, key=lambda b: b["data"])
