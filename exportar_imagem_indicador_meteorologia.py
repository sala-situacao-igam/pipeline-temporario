"""
Descrição: exporta os indicadores 4.1 (previsões do tempo), 4.2 (alertas
de tempestade severa) e 4.3 (tendência climática) como imagens PNG, no
mesmo padrão visual dos exports do indicador 2.2.

Conexões do Pipeline:
- Entradas: resultados de extrair_documentos_simge_calculo.py
  (contar_previsoes_4_1, contar_tendencia_climatica_4_3, contar_alertas_4_2,
  dataframe_dias_semana_4_1).
- Saídas: PNGs salvos localmente, enviados ao Drive
  (config.PASTA_GRAFICOS_ID) por gerar_relatorios_visuais.py.

Funções:
- _rotulo_mes: converte "AAAA-MM" em rótulo abreviado, ex. "Mai/2026".
- _grafico_barras_simples: monta um gráfico de barras verticais em PNG (base comum às funções abaixo).
- exportar_barras_dia_semana_4_1: barras por dia da semana (indicador 4.1).
- exportar_barras_mes_4_3: barras por mês de boletins de tendência climática (indicador 4.3).
- exportar_barras_dias_alerta_4_2: barras por mês do nº de dias com alerta (indicador 4.2).
- exportar_barras_alertas_individuais_4_2: barras por mês do nº de alertas individuais (indicador 4.2).

Uso (Colab) -- depois de já ter r_4_1/r_4_3 (mesmo resultado usado pra
gerar o meteorologia.html):
---------------------------------------------------------------------------
    from extrair_documentos_simge_ingestao import (
        URL_PASTA_PREVISOES_2026, URL_PASTA_TENDENCIA_CLIMATICA_2026,
    )
    from extrair_documentos_simge_calculo import (
        contar_previsoes_4_1, contar_tendencia_climatica_4_3,
    )
    from exportar_imagem_indicador_meteorologia import (
        exportar_barras_dia_semana_4_1,
        exportar_barras_mes_4_3,
    )

    r_4_1 = contar_previsoes_4_1(URL_PASTA_PREVISOES_2026, "2026-01-01", "2026-08-31")
    r_4_3 = contar_tendencia_climatica_4_3(URL_PASTA_TENDENCIA_CLIMATICA_2026, "2026-01-01", "2026-08-31")

    exportar_barras_dia_semana_4_1(r_4_1, "indicador_4_1_dias_semana.png")
    exportar_barras_mes_4_3(r_4_3, "indicador_4_3_por_mes.png")

"""
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MaxNLocator

from extrair_documentos_simge_calculo import dataframe_dias_semana_4_1

COR_FUNDO = "#fcfcfb"
COR_TEXTO = "#0b0b0b"
COR_TEXTO_SECUNDARIO = "#52514e"
COR_BORDA = "#e1e0d9"
COR_BARRA = "#1c3f66"  

TITULO_BARRAS_DIA_SEMANA_4_1 = (
    "Indicador 4.1 — Previsões do tempo publicadas\n"
    "Previsões publicadas por dia da semana"
)
TITULO_BARRAS_MES_4_3 = (
    "Indicador 4.3 — Monitoramento Climático\n"
    "Boletins de tendência climática publicados por mês"
)
TITULO_BARRAS_DIAS_ALERTA_4_2 = (
    "Indicador 4.2 — Monitoramento Meteorológico e envio de alertas realizado\n"
    "Número de relatórios diários (dias com alerta) por mês"
)
TITULO_BARRAS_ALERTAS_INDIVIDUAIS_4_2 = (
    "Indicador 4.2 — Monitoramento Meteorológico e envio de alertas realizado\n"
    "Número de alertas individuais por mês"
)

MESES_PT_ABREV = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}


def _rotulo_mes(chave_ano_mes):
    """'2026-05' -> 'Mai/2026'."""
    ano, mes = chave_ano_mes.split("-")
    return f"{MESES_PT_ABREV.get(mes, mes)}/{ano}"


def _grafico_barras_simples(
    categorias, valores, rotulo_eixo_y, caminho_saida, dpi, titulo=None,
    rotulo_eixo_x=None, rotacao_x=0,
):
    """Barras verticais com o mesmo visual em todo o projeto: 1 cor sólida,
    valor escrito em cima de cada barra, grade horizontal leve, sem bordas
    nos eixos superior/direito/esquerdo. `titulo=None` (padrão) gera sem
    título embutido; passe um texto pra ter título embutido no PNG.
    `rotulo_eixo_x` (opcional) nomeia o eixo X -- útil quando a categoria
    não é autoexplicativa (ex. "mês" no 4.2). `rotacao_x` (opcional,
    padrão 0) gira os rótulos do eixo X -- útil com mais categorias (ex.
    12 meses no 4.2), pra não sobrepor texto."""
    maximo = max(valores) if max(valores) > 0 else 1

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=dpi)
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    x = np.arange(len(categorias))
    barras = ax.bar(x, valores, color=COR_BARRA, width=0.6)

    for retangulo, valor in zip(barras, valores):
        ax.text(
            retangulo.get_x() + retangulo.get_width() / 2, retangulo.get_height() + maximo * 0.02,
            str(valor), ha="center", va="bottom", fontsize=10, fontweight="bold", color=COR_TEXTO,
        )

    ax.set_xticks(x)
    if rotacao_x:
        ax.set_xticklabels(categorias, fontsize=9, color=COR_TEXTO_SECUNDARIO, rotation=rotacao_x, ha="right")
    else:
        ax.set_xticklabels(categorias, fontsize=9, color=COR_TEXTO_SECUNDARIO)
    if rotulo_eixo_x:
        ax.set_xlabel(rotulo_eixo_x, fontsize=9, color=COR_TEXTO_SECUNDARIO)
    ax.set_ylabel(rotulo_eixo_y, fontsize=9, color=COR_TEXTO_SECUNDARIO)
    ax.set_ylim(0, maximo * 1.18)
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))  # nº de arquivos/boletins é sempre inteiro
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(COR_BORDA)
    ax.tick_params(axis="y", labelsize=8, colors=COR_TEXTO_SECUNDARIO)
    ax.tick_params(axis="x", length=0)
    ax.yaxis.grid(True, color=COR_BORDA, linewidth=0.7)
    ax.set_axisbelow(True)

    if titulo:
        ax.set_title(titulo, fontsize=10.5, color=COR_TEXTO, pad=14)

    fig.savefig(caminho_saida, facecolor=COR_FUNDO, bbox_inches="tight")
    print(f"Imagem salva em: {caminho_saida}")
    return caminho_saida


def exportar_barras_dia_semana_4_1(
    resultado_4_1, caminho_saida="indicador_4_1_dias_semana.png", dpi=200, titulo=TITULO_BARRAS_DIA_SEMANA_4_1
):
    """Indicador 4.1 -- barras por dia da semana. `resultado_4_1` é o
    dicionário devolvido por contar_previsoes_4_1() (mesmo que alimenta o
    meteorologia.html). Passe `titulo=None` pra gerar sem título embutido."""
    df = dataframe_dias_semana_4_1(resultado_4_1)
    return _grafico_barras_simples(
        categorias=df["dia_semana"].tolist(),
        valores=[int(v) for v in df["total_publicacoes"]],
        rotulo_eixo_y="Arquivos publicados",
        caminho_saida=caminho_saida,
        dpi=dpi,
        titulo=titulo,
    )


def exportar_barras_mes_4_3(
    resultado_4_3, caminho_saida="indicador_4_3_por_mes.png", dpi=200, titulo=TITULO_BARRAS_MES_4_3
):
    """Indicador 4.3 -- barras por mês de criação dos boletins
    TENDENCIA_CLIMATICA_*. `resultado_4_3` é o dicionário devolvido por
    contar_tendencia_climatica_4_3() -- usa a chave 'por_mes' (já exclui
    os PROGNOSTICO_*). Passe `titulo=None` pra gerar sem título embutido."""
    por_mes = resultado_4_3["por_mes"]
    meses_ordenados = sorted(por_mes.keys())  # "YYYY-MM" já ordena certo como texto
    return _grafico_barras_simples(
        categorias=[_rotulo_mes(m) for m in meses_ordenados],
        valores=[int(por_mes[m]) for m in meses_ordenados],
        rotulo_eixo_y="Boletins publicados",
        caminho_saida=caminho_saida,
        dpi=dpi,
        titulo=titulo,
    )


def exportar_barras_dias_alerta_4_2(
    resultado_4_2, caminho_saida="indicador_4_2_dias_alerta.png", dpi=200,
    titulo=TITULO_BARRAS_DIAS_ALERTA_4_2,
):
    """Indicador 4.2 -- barras por mês, número de "relatórios diários"
    (dias com pelo menos 1 alerta publicado). `resultado_4_2` é o
    dicionário devolvido por contar_alertas_4_2() -- usa a chave
    'por_mes_dias' (sempre com os 12 meses, Jan-Dez, zero-fill nos que
    ainda não chegaram). Passe `titulo=None` pra gerar sem título
    """
    por_mes = resultado_4_2["por_mes_dias"]
    meses_ordenados = sorted(por_mes.keys())
    return _grafico_barras_simples(
        categorias=[_rotulo_mes(m) for m in meses_ordenados],
        valores=[int(por_mes[m]) for m in meses_ordenados],
        rotulo_eixo_y="Relatórios diários (dias com alerta)",
        rotulo_eixo_x="Mês",
        rotacao_x=45,
        caminho_saida=caminho_saida,
        dpi=dpi,
        titulo=titulo,
    )


def exportar_barras_alertas_individuais_4_2(
    resultado_4_2, caminho_saida="indicador_4_2_alertas_individuais.png", dpi=200,
    titulo=TITULO_BARRAS_ALERTAS_INDIVIDUAIS_4_2,
):
    """Indicador 4.2 -- barras por mês, número de alertas individuais
    (podem ser vários no mesmo dia/relatório). `resultado_4_2` é o
    dicionário devolvido por contar_alertas_4_2() -- usa a chave
    'por_mes_alertas' (sempre com os 12 meses, Jan-Dez, zero-fill nos que
    ainda não chegaram). Passe `titulo=None` pra gerar sem título
    """
    por_mes = resultado_4_2["por_mes_alertas"]
    meses_ordenados = sorted(por_mes.keys())
    return _grafico_barras_simples(
        categorias=[_rotulo_mes(m) for m in meses_ordenados],
        valores=[int(por_mes[m]) for m in meses_ordenados],
        rotulo_eixo_y="Alertas individuais",
        rotulo_eixo_x="Mês",
        rotacao_x=45,
        caminho_saida=caminho_saida,
        dpi=dpi,
        titulo=titulo,
    )
