"""
Descrição: páginas de HIDROLOGIA no novo layout (layout_cg.gerar_pagina_hidro)
-- visão "Série histórica" (hidrometria.html) e visão "Contrato de Gestão"
(hidrometria_cg.html). Substitui o dashboard_cg.py da Fase 1a (que usava o
layout antigo).

Cálculos -- as MESMAS funções oficiais de hoje, só muda o recorte:
- 2.2: indicador_2_2_calculo.calcular_pontuacao_2_2 (cota, só tem_cota) e
  calcular_pontuacao_2_2_chuva; nota por estação (média no período) e
  cartão com a pontuação média geral + percentual médio geral.
- 2.1: indicador_2_1_calculo.calcular_cd_2_1 (pacotes sem atraso ÷ pacotes
  previstos = estações × 24 × dias).
- 2.8 (só no CG): lido do indicador_2_8_resumo.csv gravado pelo
  pipeline_consistencia.py (soma da rede, decisões de 27/09).

Série histórica: todo o fato_disponibilidade, sem exclusões (como hoje);
2.1 com dois universos: "Todas" (estações do fato) e "Com dados".
Contrato de Gestão: 01/07/2026 em diante; no 2.1 e no 2.2 saem SÓ as
estações do estacoes_excluidas.csv -- as instaladas que não mandaram dado
no período continuam (0%, reprovadas) e são listadas abaixo do ranking;
no 2.1, o gráfico mostra as estações que enviaram pacotes (número
recalculado a cada rodada); seção do 2.8 + MERGE (satélite, desde 28/09/2026 -- era CHIRPS).

Funções: gerar_hidro_serie(...), gerar_hidro_cg(...) -- esta última devolve também o
`dados` com devolver_dados=True (usado pelos gráficos do relatório).
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

import config_cg
import indicador_2_1_calculo as ind21
import indicador_2_2_calculo as ind22
import layout_cg
import nav_cg
import nav_site

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")


def _hoje():
    return datetime.now(FUSO_BRASIL).date()


def _fmt(d):
    return pd.Timestamp(d).strftime("%d/%m/%Y")


def _norm(df, col="codigo_estacao"):
    df = df.copy()
    df[col] = df[col].astype(str).str.zfill(8)
    return df


def _preparar_fato(fato):
    fato = _norm(fato)
    if not pd.api.types.is_datetime64_any_dtype(fato["data_dia"]):
        fato["data_dia"] = pd.to_datetime(fato["data_dia"], format="mixed")
    return fato


# ---------------------------------------------------------------------
# 2.2
# ---------------------------------------------------------------------
def _ranking(df_pontuacao, nomes):
    return [
        {"codigo": r.codigo_estacao, "nome": nomes.get(r.codigo_estacao, ""),
         "percentual": float(r.percentual_medio), "pontuacao": int(r.pontuacao)}
        for r in df_pontuacao.itertuples()
    ]


def _completar_com_ausentes(df_pontuacao, universo, variavel):
    """Estação do universo que não aparece no fato do período (nenhum
    registro) entra com 0% e nota 0 -- ela conta no indicador como
    reprovada (decisão de 27/09: só as estações do estacoes_excluidas.csv
    saem do cálculo)."""
    faltantes = sorted(set(universo) - set(df_pontuacao["codigo_estacao"]))
    if not faltantes:
        return df_pontuacao
    print(f"  2.2 ({variavel}): {len(faltantes)} estação(ões) sem nenhuma linha no período entram com 0%: {faltantes}")
    extra = pd.DataFrame({"codigo_estacao": faltantes, "variavel_usada": variavel, "ano_inicio_operacao": None,
                          "percentual_medio": 0.0, "pontuacao": 0, "faixa": ind22.ROTULO_PONTUACAO[0]})
    df = pd.concat([df_pontuacao.drop(columns=["ranking"], errors="ignore"), extra], ignore_index=True)
    df = df.sort_values(["pontuacao", "percentual_medio"], ascending=[False, False]).reset_index(drop=True)
    df.insert(0, "ranking", df.index + 1)
    return df


def _bloco_2_2(fato, dim, excl_cota=(), excl_chuva=(), universo_cota=None, universo_chuva=None):
    nomes = _norm(dim).set_index("codigo_estacao")["nome_estacao"].to_dict()
    df_cota = ind22.calcular_pontuacao_2_2(fato[~fato["codigo_estacao"].isin(excl_cota)], dim)
    df_chuva = ind22.calcular_pontuacao_2_2_chuva(fato[~fato["codigo_estacao"].isin(excl_chuva)], dim)
    if universo_cota is not None:
        df_cota = _completar_com_ausentes(df_cota, universo_cota, "cota")
    if universo_chuva is not None:
        df_chuva = _completar_com_ausentes(df_chuva, universo_chuva, "chuva")
    kpis = []
    for rot, df, id_ in [("2.2 Disponibilidade · Cota", df_cota, "22c"), ("2.2 Disponibilidade · Chuva", df_chuva, "22ch")]:
        kpis.append({"id": id_, "rotulo": rot, "nota": float(ind22.media_geral(df)),
                     "percentual": float(ind22.media_percentual_geral(df)),
                     "detalhe": f"média de {len(df)} estações", "mostrar_chip": False})
    return {"cota": _ranking(df_cota, nomes), "chuva": _ranking(df_chuva, nomes)}, kpis


# ---------------------------------------------------------------------
# 2.1
# ---------------------------------------------------------------------
def _pct_universo(r):
    tot = r["total_previsto"] or 1
    return {"sem_atraso": r["recebido_sem_atraso"] / tot * 100,
            "com_atraso": r["recebido_com_atraso"] / tot * 100,
            "nao_recebido": r["nao_recebido"] / tot * 100}


def _bloco_2_1(df_pacotes, universo, incluir_todas):
    """Devolve (ind_2_1, kpi) ou (None, None) sem pacotes."""
    if df_pacotes is None or df_pacotes.empty:
        return None, None
    pacotes = df_pacotes[df_pacotes["codigo_estacao"].isin(universo)]
    if pacotes.empty:
        return None, None
    com_dado = sorted(pacotes["codigo_estacao"].unique())
    d0, d1 = pacotes["Data_Hora_Medicao"].min(), pacotes["Data_Hora_Medicao"].max()
    dias = (d1.normalize() - d0.normalize()).days + 1
    universos = []
    if incluir_todas:
        r = ind21.calcular_cd_2_1(pacotes, universo, dias_periodo=dias)
        universos.append({"rotulo": f"Todas ({len(universo)})", "n": len(universo), "nota": r["cd"], **_pct_universo(r)})
    r = ind21.calcular_cd_2_1(pacotes, com_dado, dias_periodo=dias)
    universos.append({"rotulo": f"Com dados ({len(com_dado)})", "n": len(com_dado), "nota": r["cd"], **_pct_universo(r)})
    principal = universos[0]
    kpi = {"id": "21", "rotulo": "2.1 Transmissão sem atraso", "nota": principal["nota"],
           "percentual": principal["sem_atraso"], "detalhe": f"dos pacotes · {principal['rotulo'].lower()}"}
    return {"periodo": f"{d0:%d/%m/%Y} a {d1:%d/%m/%Y}", "universos": universos}, kpi


def _cartao_2_1_vazio():
    return {"periodo": "sem dados da API nova nesta rodada",
            "universos": [{"rotulo": "Sem dados", "n": 0, "nota": 0, "sem_atraso": 0, "com_atraso": 0, "nao_recebido": 0}]}


# ---------------------------------------------------------------------
# 2.8 (a partir do resumo gravado pelo pipeline)
# ---------------------------------------------------------------------
def _bloco_2_8(resumo):
    if resumo is None or resumo.empty:
        return None, None, [], ["Resumo do 2.8 ainda não disponível — seção do 2.8 não exibida nesta rodada."]
    r = resumo.set_index("medida")

    def barra(medida, com_nota):
        linha = r.loc[medida]
        item = {"chave": medida, "rotulo": linha["rotulo"], "aprovado": int(linha["aprovados"]),
                "reprovado": int(linha["reprovados"]), "base": int(linha["avaliados"])}
        if com_nota and pd.notna(linha["nota"]):
            item["nota"] = int(linha["nota"])
        return item

    # Gráficos = QUALIDADE (aprovado × reprovado, tudo na base) -- sem nota,
    # para não confundir com a nota do card, que vem dos dados CONSISTIDOS.
    barras = [barra("chuva", False), barra("nivel_range", False), barra("nivel_final", False)]
    n_ch, n_nv = int(r.loc["chuva", "n_estacoes"]), int(r.loc["nivel_final", "n_estacoes"])
    ind_2_8 = {"barras": barras, "notas": [
        f"Chuva: {n_ch} estações · Nível: {n_nv} estações (só fluviométricas; desinstaladas excluídas).",
        "Gráficos (qualidade): todas as leituras entram na base; leituras em branco, suspeitas e "
        "'Teste não realizado' contam como reprovadas. Nível — resultado final: aprovada no Range e no Persist.",
        "Nota (cards): dados consistidos ÷ dados coletados — leituras que chegaram com valor e receberam "
        "resultado da consistência (aprovadas ou reprovadas). Leituras em branco não são dado coletado "
        "(já cobradas no 2.2); não consistidas são as leituras com valor que não puderam ser testadas.",
    ]}
    # Extras usados só pelos gráficos do relatório (gerar_relatorios_visuais.py) -- o layout ignora.
    ind_2_8["n_estacoes_chuva"], ind_2_8["n_estacoes_nivel"] = n_ch, n_nv
    if "chuva_cd" in r.index:  # leituras com valor (coletadas) x todas as leituras esperadas da base
        ind_2_8["disponibilidade_chuva"] = {"coletadas": int(r.loc["chuva_cd", "avaliados"]),
                                            "esperadas": int(r.loc["chuva", "avaliados"])}

    def kpi(id_, rotulo, medida_cd, medida_antiga):
        if medida_cd in r.index:  # regra atual (27/09): dados consistidos
            linha = r.loc[medida_cd]
            detalhe = f"dos dados coletados consistidos ({int(linha['aprovados']):,} de {int(linha['avaliados']):,})".replace(",", ".")
        else:  # resumo antigo, gravado antes da regra nova
            linha = r.loc[medida_antiga]
            detalhe = "aprovadas (regra anterior)"
        return {"id": id_, "rotulo": rotulo, "nota": int(linha["nota"]),
                "percentual": float(linha["percentual"]), "detalhe": detalhe}

    kpis = [kpi("28ch", "2.8 Consistência · Chuva", "chuva_cd", "chuva"),
            kpi("28n", "2.8 Consistência · Nível", "nivel_cd", "nivel_final")]
    avisos = []
    merge = None
    if "merge" in r.index and r.loc["merge", "avaliados"] > 0:
        merge = {"convergencia": int(r.loc["merge", "aprovados"]), "divergencia": int(r.loc["merge", "reprovados"]),
                 "periodo": f"{_fmt(r.loc['merge', 'periodo_inicio'])} a {_fmt(r.loc['merge', 'periodo_fim'])} "
                            "(último dia já publicado pelo MERGE)"}
    else:
        avisos.append("Comparação com o MERGE indisponível nesta rodada.")
    return ind_2_8, merge, kpis, avisos


# ---------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------
def _finalizar(caminho, visao):
    nav_site.injetar_nav(caminho, "hidrometria")
    nav_cg.injetar_subnav(caminho, "hidrologia", visao)


def gerar_hidro_serie(fato_disponibilidade, dim_estacao, df_pacotes, caminho_saida):
    fato = _preparar_fato(fato_disponibilidade)
    universo = sorted(fato["codigo_estacao"].unique())
    ind_2_1, kpi_21 = _bloco_2_1(df_pacotes, universo, incluir_todas=True)
    ind_2_2, kpis_22 = _bloco_2_2(fato, dim_estacao)
    avisos = [] if ind_2_1 else ["Sem dados da API nova (2.1) nesta rodada."]
    dados = {
        "titulo": "Hidrologia — Série histórica",
        "periodo": f"Período: {_fmt(fato['data_dia'].min())} a {_fmt(fato['data_dia'].max())}",
        "atualizado_em": datetime.now(FUSO_BRASIL).strftime("%d/%m/%Y às %H:%M"), "avisos": avisos,
        "kpis": ([kpi_21] if kpi_21 else []) + kpis_22,
        "ind_2_1": ind_2_1 or _cartao_2_1_vazio(), "ind_2_2": ind_2_2,
    }
    layout_cg.gerar_pagina_hidro(dados, caminho_saida)
    _finalizar(caminho_saida, "serie")
    return {k["id"]: f"{k['percentual']:.1f}% -> nota {k['nota']}" for k in dados["kpis"]}


def gerar_hidro_cg(fato_disponibilidade, dim_estacao, df_pacotes, resumo_2_8, caminho_saida,
                   data_fim=None, por_estacao_2_8=None, devolver_dados=False):
    """Contrato de Gestão. Decisão de 27/09 (revista): no 2.1 e no 2.2 saem
    SÓ as estações do estacoes_excluidas.csv. Estações instaladas que não
    mandaram nada no período CONTINUAM no cálculo (0% -> reprovadas) e
    aparecem na lista "sem nenhum dado no período" abaixo do ranking.
    `por_estacao_2_8` não é mais usado (mantido na assinatura por compatibilidade).
    `devolver_dados=True` (29/09/2026) devolve (resumo, dados) -- o `dados` é
    o que gerar_relatorios_visuais.py desenha nos gráficos do relatório,
    para que relatório e dashboard mostrem sempre os mesmos números."""
    data_fim = data_fim or _hoje()
    fato = _preparar_fato(fato_disponibilidade)
    fato_cg = fato[(fato["data_dia"] >= pd.Timestamp(config_cg.DATA_INICIO_CG_HIDRO))
                   & (fato["data_dia"] < pd.Timestamp(data_fim) + pd.Timedelta(days=1))]
    excl_chuva, excl_nivel = set(config_cg.ESTACOES_EXCLUIDAS_CHUVA), set(config_cg.ESTACOES_EXCLUIDAS_NIVEL)

    dim = _norm(dim_estacao)
    verdadeiro = lambda col: dim[col].astype(str).str.strip().str.lower().isin({"true", "1", "sim"}) if col in dim else True
    univ_cota = set(dim.loc[verdadeiro("tem_cota"), "codigo_estacao"]) - excl_nivel
    univ_chuva = set(dim.loc[verdadeiro("tem_chuva"), "codigo_estacao"]) - excl_chuva

    universo_21 = sorted(set(fato["codigo_estacao"]) - set(config_cg.ESTACOES_EXCLUIDAS_2_1))
    pacotes = None
    if df_pacotes is not None:
        pacotes = df_pacotes[df_pacotes["Data_Hora_Medicao"] >= pd.Timestamp(config_cg.DATA_INICIO_CG_HIDRO)]
    ind_2_1, kpi_21 = _bloco_2_1(pacotes, universo_21, incluir_todas=False)
    ind_2_2, kpis_22 = _bloco_2_2(fato_cg, dim_estacao, excl_cota=excl_nivel, excl_chuva=excl_chuva,
                                  universo_cota=univ_cota, universo_chuva=univ_chuva)
    ind_2_8, merge, kpis_28, avisos = _bloco_2_8(resumo_2_8)
    if not ind_2_1:
        avisos.insert(0, "Sem dados da API nova (2.1) nesta rodada.")
    dados = {
        "titulo": "Hidrologia — Contrato de Gestão",
        "periodo": f"Período: {_fmt(config_cg.DATA_INICIO_CG_HIDRO)} a {_fmt(data_fim)}",
        "atualizado_em": _fmt(_hoje()), "avisos": avisos,
        "kpis": ([kpi_21] if kpi_21 else []) + kpis_22 + kpis_28,
        "ind_2_1": ind_2_1 or _cartao_2_1_vazio(), "ind_2_2": ind_2_2,
        "ind_2_8": ind_2_8, "merge": merge,
    }
    layout_cg.gerar_pagina_hidro(dados, caminho_saida)
    _finalizar(caminho_saida, "cg")
    resumo = {k["id"]: f"{k['percentual']:.1f}% -> nota {k['nota']}" for k in dados["kpis"]}
    return (resumo, dados) if devolver_dados else resumo
