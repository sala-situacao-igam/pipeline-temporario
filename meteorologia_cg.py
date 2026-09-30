"""
Descrição: páginas de METEOROLOGIA no novo layout (layout_cg.gerar_pagina_meteo)
-- visão "2026" (meteorologia.html) e visão "Contrato de Gestão"
(meteorologia_cg.html).

Regras:
- 2026 (retrato atual, SEM mudança de cálculo): 01/01/2026 até hoje, com as
  funções originais de extrair_documentos_simge_calculo (4.1 = dias úteis,
  descontando feriados e pontos facultativos de 2026).
- Contrato de Gestão (decisões de 27/09/2026):
  - período: config_cg.DATA_INICIO_CG_METEO (16/09/2026) até hoje, atravessando
    a virada do ano;
  - 4.1: 1 previsão esperada por DIA CORRIDO (sábado e domingo inclusos),
    SEM desconto de feriados (os meteorologistas trabalham de plantão);
  - 4.1 e 4.3: o SIMGE tem uma pasta por ano. A pasta de cada ano vem de
    config_cg.URLS_SIMGE_POR_ANO se estiver preenchida; senão é LOCALIZADA
    AUTOMATICAMENTE na página inicial do repositório (que lista as pastas
    2019...2026 com o folderId). Se o ano ainda não tiver pasta, fica de fora
    com AVISO (no log e na página);
  - 4.2: página única de alertas (coleta original); gráfico mensal com os
    meses do período do CG;
  - 4.3: mesma regra original (1 boletim por mês-calendário do período).

Conexões do Pipeline:
- Entradas: SIMGE (extrair_documentos_simge_*), config_cg.py.
- Saídas: meteorologia.html e meteorologia_cg.html (nav principal + sub-abas).

Funções principais:
- gerar_meteo_2026(caminho) / gerar_meteo_cg(caminho): geram as páginas e
  devolvem um resumo para o log.
- descobrir_url_pasta_ano(tipo, ano): localiza a pasta do ano no SIMGE.
"""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config_cg
import layout_cg
import nav_cg
import nav_site
from extrair_documentos_simge_calculo import (
    calcular_cd_4_1,
    calcular_cd_4_2,
    calcular_cd_4_3,
    contar_alertas_4_2,
    contar_previsoes_4_1,
    contar_tendencia_climatica_4_3,
    pontuar_percentual_4_1_4_3,
)
from extrair_documentos_simge_ingestao import (
    INSTANCIA_PREVISOES,
    INSTANCIA_TENDENCIA,
    URL_ALERTAS_TEMPESTADE_SEVERA,
    URL_PASTA_PREVISOES_2026,
    URL_PASTA_TENDENCIA_CLIMATICA_2026,
)

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")
DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
DIAS_ABREV = {"Segunda": "Seg", "Terça": "Ter", "Quarta": "Qua", "Quinta": "Qui",
              "Sexta": "Sex", "Sábado": "Sáb", "Domingo": "Dom"}
MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# Página inicial de cada repositório no SIMGE (lista as pastas por ano)
RAIZ_SIMGE = {
    "previsoes": ("https://simge.mg.gov.br/previs%C3%B5es", INSTANCIA_PREVISOES),
    "tendencia": ("https://simge.mg.gov.br/tendencia-climatica", INSTANCIA_TENDENCIA),
}


def _hoje():
    return datetime.now(FUSO_BRASIL).date()


def _como_data(valor):
    return valor if isinstance(valor, date) else datetime.strptime(str(valor), "%Y-%m-%d").date()


def _rotulo_mes(chave):  # "2026-09" -> "Set/26"
    ano, mes = chave.split("-")
    return f"{MESES_ABREV[int(mes) - 1]}/{ano[2:]}"


def _fmt_data(d):
    return pd.Timestamp(d).strftime("%d/%m/%Y")


# ---------------------------------------------------------------------
# Pasta do ano no SIMGE (automático)
# ---------------------------------------------------------------------
def _montar_url_pasta(raiz, instancia, folder_id):
    return (f"{raiz}/-/document_library/{instancia}/view/{folder_id}"
            f"?_com_liferay_document_library_web_portlet_DLPortlet_INSTANCE_{instancia}_folderId={folder_id}")


def encontrar_folder_id_no_html(html, instancia, ano):
    """Procura, no HTML da página inicial, um link de pasta
    (<a href=".../document_library/<instancia>/view/<folderId>...">) cujo
    texto ou atributo (title / data-title / aria-label) seja exatamente o
    ano. Devolve o folderId (str) ou None."""
    ancora = re.compile(
        rf'<a\b([^>]*?href="[^"]*?/document_library/{re.escape(instancia)}/view/(\d+)[^"]*"[^>]*)>(.*?)</a>',
        flags=re.S | re.I,
    )
    alvo = str(ano)
    for m in ancora.finditer(html):
        atributos, folder_id, conteudo = m.group(1), m.group(2), m.group(3)
        texto = re.sub(r"<[^>]+>", " ", conteudo).split()
        if alvo in texto or re.search(rf'(title|data-title|aria-label)="\s*{alvo}\s*"', atributos):
            return folder_id
    return None


def descobrir_url_pasta_ano(tipo, ano):
    """URL da pasta do `ano` no SIMGE: config_cg primeiro; senão, busca na
    página inicial. None se o ano ainda não existir (ou a busca falhar)."""
    url = config_cg.URLS_SIMGE_POR_ANO.get(ano, {}).get(tipo)
    if url:
        return url
    import requests
    from extrair_documentos_simge_ingestao import HEADERS
    raiz, instancia = RAIZ_SIMGE[tipo]
    try:
        resposta = requests.get(raiz, headers=HEADERS, timeout=30)
        resposta.raise_for_status()
        folder_id = encontrar_folder_id_no_html(resposta.text, instancia, ano)
    except Exception as erro:  # noqa: BLE001
        print(f"  AVISO: não consegui abrir {raiz} para achar a pasta de {ano} ({erro}).")
        return None
    if folder_id:
        print(f"  Pasta de {ano} ({tipo}) localizada automaticamente: folderId={folder_id}")
        return _montar_url_pasta(raiz, instancia, folder_id)
    return None


# ---------------------------------------------------------------------
# Contagens (período que pode atravessar a virada do ano)
# ---------------------------------------------------------------------
def _fatias_por_ano(inicio, fim):
    ini, fim = _como_data(inicio), _como_data(fim)
    return [(a, max(ini, date(a, 1, 1)), min(fim, date(a, 12, 31))) for a in range(ini.year, fim.year + 1)]


def _meses(inicio, fim):
    return [str(p) for p in pd.period_range(_como_data(inicio), _como_data(fim), freq="M")]


def contar_4_1_multiano(inicio, fim, avisos):
    total = {"total_arquivos": 0, "arquivos": [], "por_dia_semana": {d: 0 for d in DIAS_SEMANA_PT}}
    for ano, a, b in _fatias_por_ano(inicio, fim):
        url = descobrir_url_pasta_ano("previsoes", ano)
        if not url:
            avisos.append(f"pasta de previsões de {ano} ainda não encontrada no SIMGE — {ano} fora da contagem do 4.1")
            continue
        r = contar_previsoes_4_1(url, a, b)
        total["total_arquivos"] += r["total_arquivos"]
        total["arquivos"] += r["arquivos"]
        for d, n in r["por_dia_semana"].items():
            total["por_dia_semana"][d] += n
    return total


def contar_4_3_multiano(inicio, fim, avisos):
    por_mes = {m: 0 for m in _meses(inicio, fim)}
    total = {"total_boletins": 0, "boletins": []}
    for ano, a, b in _fatias_por_ano(inicio, fim):
        url = descobrir_url_pasta_ano("tendencia", ano)
        if not url:
            avisos.append(f"pasta de tendência climática de {ano} ainda não encontrada no SIMGE — {ano} fora da contagem do 4.3")
            continue
        r = contar_tendencia_climatica_4_3(url, a, b)
        total["total_boletins"] += r["total_boletins"]
        total["boletins"] += r["boletins"]
        for k, n in r["por_mes"].items():
            por_mes[k] = por_mes.get(k, 0) + n
    total["por_mes"] = dict(sorted(por_mes.items()))
    return total


def contar_4_2_periodo(inicio, fim):
    r = contar_alertas_4_2(URL_ALERTAS_TEMPESTADE_SEVERA, inicio, fim)
    dias = {m: 0 for m in _meses(inicio, fim)}
    alertas = dict(dias)
    for d in r["dias"]:
        k = f"{d['data'].year}-{d['data'].month:02d}"
        if k in dias:
            dias[k] += 1
            alertas[k] += len(d["alertas"])
    r["por_mes_dias"], r["por_mes_alertas"] = dias, alertas
    return r


def calcular_cd_4_1_todos_os_dias(r_4_1, inicio, fim):
    """CG: 1 previsão esperada por dia corrido, sem desconto de feriados."""
    esperadas = (pd.Timestamp(_como_data(fim)) - pd.Timestamp(_como_data(inicio))).days + 1
    publicadas = r_4_1["total_arquivos"]
    pct = round(publicadas / esperadas * 100, 2) if esperadas else 0.0
    return {"esperadas": esperadas, "previsoes_publicadas": publicadas, "percentual": pct,
            "pontuacao": pontuar_percentual_4_1_4_3(pct)}


# ---------------------------------------------------------------------
# Montagem dos dados da página
# ---------------------------------------------------------------------
def _dados_pagina(titulo, inicio, fim, r41, r42, r43, cd41, cd42, cd43, texto_4_1, avisos):
    pct = lambda v: f"{v:.2f}".replace(".", ",") + "%"
    boletins = [(dt.strftime("%d/%m/%Y %H:%M"), t) for dt, t in r43["boletins"]]
    return {
        "titulo": titulo,
        "periodo": f"Período: {_fmt_data(inicio)} a {_fmt_data(fim)}",
        "atualizado_em": datetime.now(FUSO_BRASIL).strftime("%d/%m/%Y às %H:%M"),
        "avisos": avisos,
        "kpis": [
            {"id": "41", "rotulo": "4.1 Previsões do tempo", "nota": cd41["pontuacao"],
             "percentual": cd41["percentual"], "detalhe": "publicadas"},
            {"id": "42", "rotulo": "4.2 Monitoramento e alertas", "nota": cd42["pontuacao"],
             "percentual": cd42["percentual"], "detalhe": "dos dias com relatório"},
            {"id": "43", "rotulo": "4.3 Monitoramento climático", "nota": cd43["pontuacao"],
             "percentual": cd43["percentual"], "detalhe": "dos boletins mensais"},
        ],
        "ind_4_1": {
            "por_dia_semana": [(DIAS_ABREV[d], r41["por_dia_semana"].get(d, 0)) for d in DIAS_SEMANA_PT],
            "resumo": f"<strong>{cd41['previsoes_publicadas']}</strong> previsões publicadas de "
                      f"<strong>{texto_4_1}</strong> · {pct(cd41['percentual'])} → nota {cd41['pontuacao']}/10",
        },
        "ind_4_2": {
            "por_mes_dias": [(_rotulo_mes(m), n) for m, n in sorted(r42["por_mes_dias"].items())],
            "por_mes_alertas": [(_rotulo_mes(m), n) for m, n in sorted(r42["por_mes_alertas"].items())],
            "resumo": f"<strong>{cd42['relatorios_emitidos']}</strong> dias com relatório de "
                      f"<strong>{cd42['dias_no_periodo']}</strong> dias · {r42['total_alertas_individuais']} alertas · "
                      f"{pct(cd42['percentual'])} → nota {cd42['pontuacao']}/10",
        },
        "ind_4_3": {
            "por_mes": [(_rotulo_mes(m), n) for m, n in sorted(r43["por_mes"].items())],
            "boletins": boletins,
            "resumo": f"<strong>{cd43['boletins_publicados']}</strong> boletins de "
                      f"<strong>{cd43['meses_esperados']}</strong> meses esperados · "
                      f"{pct(cd43['percentual'])} → nota {cd43['pontuacao']}/10",
        },
        # Totais usados só pelos gráficos do relatório (gerar_relatorios_visuais.py) -- o layout ignora.
        "totais": {
            "4_1": {"publicadas": cd41["previsoes_publicadas"],
                    "esperadas": cd41.get("esperadas", cd41.get("dias_uteis"))},
            "4_2": {"relatorios": cd42["relatorios_emitidos"], "alertas": r42["total_alertas_individuais"],
                    "dias_no_periodo": cd42["dias_no_periodo"]},
            "4_3": {"publicados": cd43["boletins_publicados"], "esperados": cd43["meses_esperados"]},
        },
    }


def _finalizar(caminho, visao):
    nav_site.injetar_nav(caminho, "meteorologia")
    nav_cg.injetar_subnav(caminho, "meteorologia", visao)


def gerar_meteo_2026(caminho_saida, data_fim=None, devolver_resultados=False):
    """Visão 2026 -- MESMO cálculo de hoje (funções originais), layout novo."""
    inicio, fim = "2026-01-01", data_fim or _hoje()
    r41 = contar_previsoes_4_1(URL_PASTA_PREVISOES_2026, inicio, fim)
    r43 = contar_tendencia_climatica_4_3(URL_PASTA_TENDENCIA_CLIMATICA_2026, inicio, fim)
    r42 = contar_alertas_4_2(URL_ALERTAS_TEMPESTADE_SEVERA, inicio, fim)
    cd41, cd42, cd43 = calcular_cd_4_1(r41, inicio, fim), calcular_cd_4_2(r42, inicio, fim), calcular_cd_4_3(r43, inicio, fim)
    # 4.2 original preenche jan-dez; mostra só até o mês atual
    mes_atual = f"{pd.Timestamp(fim):%Y-%m}"
    for chave in ("por_mes_dias", "por_mes_alertas"):
        r42[chave] = {m: n for m, n in r42[chave].items() if m <= mes_atual}
    texto = f"{cd41['dias_uteis']} dias úteis esperados (sem feriados/facultativos)"
    dados = _dados_pagina("Meteorologia — 2026", inicio, fim, r41, r42, r43, cd41, cd42, cd43, texto, [])
    layout_cg.gerar_pagina_meteo(dados, caminho_saida)
    _finalizar(caminho_saida, "2026")
    resumo = {k["id"]: f"{k['percentual']}% -> nota {k['nota']}" for k in dados["kpis"]}
    if devolver_resultados:  # usado pelo rodar_diario_meteoro para gravar os CSVs de 2026 no Drive
        return resumo, {"r_4_1": r41, "r_4_2": r42, "r_4_3": r43}
    return resumo


def gerar_meteo_cg(caminho_saida, data_fim=None, devolver_dados=False):
    """Visão Contrato de Gestão -- regras de 27/09 (ver docstring do módulo).
    `devolver_dados=True` (29/09/2026) devolve (resumo, dados), para os
    gráficos do relatório (gerar_relatorios_visuais.py)."""
    inicio, fim = config_cg.DATA_INICIO_CG_METEO, data_fim or _hoje()
    avisos = []
    r41 = contar_4_1_multiano(inicio, fim, avisos)
    r43 = contar_4_3_multiano(inicio, fim, avisos)
    r42 = contar_4_2_periodo(inicio, fim)
    cd41 = calcular_cd_4_1_todos_os_dias(r41, inicio, fim)
    cd42, cd43 = calcular_cd_4_2(r42, inicio, fim), calcular_cd_4_3(r43, inicio, fim)
    texto = f"{cd41['esperadas']} previstas (1 por dia, incluindo fins de semana e feriados)"
    dados = _dados_pagina("Meteorologia — Contrato de Gestão", inicio, fim, r41, r42, r43,
                          cd41, cd42, cd43, texto, [a[0].upper() + a[1:] for a in avisos])
    layout_cg.gerar_pagina_meteo(dados, caminho_saida)
    _finalizar(caminho_saida, "cg")
    resumo = {k["id"]: f"{k['percentual']}% -> nota {k['nota']}" for k in dados["kpis"]} | {"avisos": avisos}
    return (resumo, dados) if devolver_dados else resumo
