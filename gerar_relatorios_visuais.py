"""
Descrição: gráficos (PNG) dos indicadores do Contrato de Gestão para o
RELATÓRIO MENSAL -- 2.1, 2.2, 2.8 (Hidrologia) e 4.1, 4.2, 4.3
(Meteorologia). REESCRITO em 29/09/2026: deixou de ser um script manual do
Colab e passou a rodar DENTRO do pipeline diário, sobrescrevendo os PNGs a
cada rodada -- assim a pasta de gráficos está sempre na versão mais atual.

Princípio: os gráficos NÃO recalculam nada. Eles desenham exatamente o
dicionário `dados` que as páginas do Contrato de Gestão do dashboard já
montam (paginas_hidrologia.gerar_hidro_cg / meteorologia_cg.gerar_meteo_cg).
Então o número do relatório é sempre o mesmo número do dashboard, com o
mesmo período, as mesmas exclusões e as mesmas regras.

Padrão visual (igual em TODOS os gráficos):
- Tela fixa de 2000 x 1200 px (10 x 6 pol, 200 dpi), sem corte automático
  ("bbox tight") -- todos os PNGs saem do mesmo tamanho e o título fica
  centralizado de verdade (o corte automático deslocava o centro).
- Cabeçalho centralizado em 3 níveis: título (indicador), subtítulo (o que
  o gráfico mostra) e período, com um filete separando do gráfico.
- Área do gráfico com margens simétricas; nome do eixo Y na horizontal,
  acima do eixo (não rotacionado).
- Paleta azul escuro -> claro (a mesma do dashboard); números no padrão
  brasileiro (334.854 · 98,5%); rodapé com nota e data de atualização.

Conexões do Pipeline:
- Entradas: o `dados` devolvido por paginas_hidrologia.gerar_hidro_cg(...,
  devolver_dados=True) e por meteorologia_cg.gerar_meteo_cg(...,
  devolver_dados=True); config_cg.PASTA_GRAFICOS_RELATORIO_ID; drive_io.py.
- Saídas: PNGs gravados numa pasta local (padrão "graficos_relatorio") e
  enviados à pasta do Drive config_cg.PASTA_GRAFICOS_RELATORIO_ID,
  SOBRESCREVENDO o arquivo de mesmo nome (mesmo ID no Drive).
- Chamado por: rodar_diario_hidro.py (Fase 5) e rodar_diario_meteoro.py.
  Falha aqui NUNCA derruba o dashboard (quem chama protege com try/except,
  e cada gráfico também é protegido individualmente).

Funções principais:
- graficos_hidro(dados_cg, pasta)  -> lista de PNGs (2.1, 2.2, 2.8)
- graficos_meteo(dados_cg, pasta)  -> lista de PNGs (4.1, 4.2, 4.3)
- publicar_no_drive(servico, caminhos, pasta_id) -> sobrescreve no Drive
- gerar_e_publicar_hidro / gerar_e_publicar_meteo: as duas acima juntas
  (é o que o pipeline chama).

Uso manual (Colab/terminal), sem esperar o pipeline:
    python gerar_relatorios_visuais.py                 # hidro + meteo, do Drive, e envia ao Drive
    python gerar_relatorios_visuais.py --so-local      # só gera os PNGs na pasta local
    python gerar_relatorios_visuais.py --exemplo       # desenha com dados de exemplo (sem Drive)
    python gerar_relatorios_visuais.py --apenas hidro  # ou --apenas meteo
"""
import argparse
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # sem tela (GitHub Actions / terminal)
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

FUSO_BRASIL = ZoneInfo("America/Sao_Paulo")
PASTA_LOCAL_PADRAO = "graficos_relatorio"

# =====================================================================
# Identidade visual -- mude AQUI e todos os gráficos mudam juntos
# =====================================================================
# Azul escuro -> claro (mesma família do dashboard / layout_cg.py).
AZUL_1 = "#1c3f66"  # principal (aprovado, sem atraso, convergência)
AZUL_2 = "#3f6e9e"
AZUL_3 = "#7ba3c9"  # secundário (reprovado, com atraso, divergência)
AZUL_4 = "#b3cae0"  # claro (não recebido, esperado)
RAMPA_5 = [AZUL_1, AZUL_2, "#5d8ab8", AZUL_3, AZUL_4]  # 5 faixas do 2.2 (Ótima -> Reprovada)

COR_FUNDO = "#ffffff"
COR_TEXTO = "#1a1a18"
COR_TEXTO_2 = "#4a4945"  # subtítulo, rótulos de eixo
COR_TEXTO_3 = "#7a7973"  # período, rodapé
COR_GRADE = "#e6e5df"
COR_FILETE = "#d6d5ce"

FONTE = "DejaVu Sans"  # existe no Colab, no Actions e no matplotlib padrão -> mesma letra em todo lugar

# Tela e grade de posições (fração da figura) -- iguais em todos os gráficos
LARGURA_POL, ALTURA_POL, DPI = 10, 6, 200
Y_TITULO, Y_SUBTITULO, Y_PERIODO, Y_FILETE = 0.945, 0.885, 0.838, 0.800
EIXO_PADRAO = [0.10, 0.155, 0.80, 0.555]  # [esquerda, base, largura, altura] -- margens laterais iguais
Y_NOTA, Y_ATUALIZADO = 0.045, 0.045

TAM_TITULO, TAM_SUBTITULO, TAM_PERIODO = 16, 12, 10
TAM_EIXO, TAM_VALOR, TAM_VALOR_2, TAM_NOTA = 10.5, 12, 9.5, 8.5

plt.rcParams.update({
    "font.family": FONTE,
    "axes.edgecolor": COR_GRADE,
    "axes.labelcolor": COR_TEXTO_2,
    "xtick.color": COR_TEXTO_2,
    "ytick.color": COR_TEXTO_3,
    "svg.fonttype": "none",
})


# =====================================================================
# Formatação pt-BR
# =====================================================================
def fmt_int(valor):
    return f"{int(round(valor)):,}".replace(",", ".")


def fmt_pct(valor, casas=1):
    return f"{valor:.{casas}f}".replace(".", ",") + "%"


def _hoje_txt():
    return datetime.now(FUSO_BRASIL).strftime("%d/%m/%Y")


# =====================================================================
# Moldura padrão (cabeçalho, eixo, rodapé)
# =====================================================================
def _nova_figura(titulo, subtitulo, periodo, eixo=None):
    """Figura com o cabeçalho padrão centralizado e um eixo já estilizado."""
    fig = plt.figure(figsize=(LARGURA_POL, ALTURA_POL), dpi=DPI)
    fig.patch.set_facecolor(COR_FUNDO)
    fig.text(0.5, Y_TITULO, titulo, ha="center", va="center", fontsize=TAM_TITULO,
             fontweight="bold", color=COR_TEXTO)
    if subtitulo:
        fig.text(0.5, Y_SUBTITULO, subtitulo, ha="center", va="center", fontsize=TAM_SUBTITULO, color=COR_TEXTO_2)
    if periodo:
        fig.text(0.5, Y_PERIODO, periodo, ha="center", va="center", fontsize=TAM_PERIODO, color=COR_TEXTO_3)
    fig.add_artist(plt.Line2D([0.10, 0.90], [Y_FILETE, Y_FILETE], transform=fig.transFigure,
                              color=COR_FILETE, linewidth=0.8))
    ax = fig.add_axes(eixo or EIXO_PADRAO)
    ax.set_facecolor(COR_FUNDO)
    for lado in ("top", "right", "left"):
        ax.spines[lado].set_visible(False)
    ax.spines["bottom"].set_color(COR_FILETE)
    ax.tick_params(axis="x", length=0, labelsize=TAM_EIXO, colors=COR_TEXTO_2, pad=8)
    ax.tick_params(axis="y", length=0, labelsize=TAM_EIXO - 1.5, colors=COR_TEXTO_3, pad=6)
    ax.yaxis.grid(True, color=COR_GRADE, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig, ax


def _rotulo_eixo_y(ax, texto):
    """Nome do eixo Y na horizontal, acima do eixo (mais fácil de ler que rotacionado)."""
    ax.text(0, 1.03, texto, transform=ax.transAxes, ha="left", va="bottom",
            fontsize=TAM_EIXO - 1, color=COR_TEXTO_3)


def _rodape(fig, nota=None):
    if nota:
        fig.text(0.10, Y_NOTA, nota, ha="left", va="center", fontsize=TAM_NOTA, color=COR_TEXTO_3)
    fig.text(0.90, Y_ATUALIZADO, f"Atualizado em {_hoje_txt()}", ha="right", va="center",
             fontsize=TAM_NOTA, color=COR_TEXTO_3)


def _salvar(fig, pasta, nome):
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome)
    fig.savefig(caminho, dpi=DPI, facecolor=COR_FUNDO)  # sem bbox tight: tamanho fixo, centro fixo
    plt.close(fig)
    print(f"  Gráfico salvo: {caminho}")
    return caminho


# =====================================================================
# Marcas
# =====================================================================
def _barra_arredondada(ax, x, altura, largura, cor, raio_px=7):
    """Coluna com o topo arredondado e a base reta (apoiada na linha de base)."""
    if altura <= 0:
        return
    fig = ax.figure
    fig.canvas.draw_idle()
    bbox = ax.get_window_extent()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    px_por_x = bbox.width / (x1 - x0)
    px_por_y = bbox.height / (y1 - y0)
    raio_px = min(raio_px, altura * px_por_y / 2)  # barra muito baixa: arredonda menos
    if raio_px < 0.5:
        ax.add_patch(Rectangle((x - largura / 2, 0), largura, altura, facecolor=cor, edgecolor="none", zorder=3))
        return
    raio_x = min(raio_px / px_por_x, largura / 2)
    raio_y = raio_x * px_por_x / px_por_y
    esquerda = x - largura / 2
    ax.add_patch(FancyBboxPatch(
        (esquerda, 0), largura, altura, boxstyle=f"round,pad=0,rounding_size={raio_x}",
        mutation_aspect=raio_y / raio_x if raio_x else 1, facecolor=cor, edgecolor="none", zorder=3))
    ax.add_patch(Rectangle((esquerda, 0), largura, min(altura, raio_y * 1.05),
                           facecolor=cor, edgecolor="none", zorder=3))


def _colunas(ax, categorias, valores, cores, rotulos, sublabels=None, largura=None, teto=1.22, escala_pct=False):
    """Colunas verticais com valor no topo (e, opcional, uma segunda linha
    menor com o percentual). Eixo Y com números pt-BR e inteiros, ou 0-100%
    quando escala_pct=True."""
    n = len(categorias)
    largura = largura or (0.46 if n <= 3 else 0.58)
    folga = 1.0 if n == 1 else 0.0  # coluna única: não deixa ficar larga demais
    ax.set_xlim(-0.6 - folga, n - 0.4 + folga)
    ax.set_xticks(range(n))
    ax.set_xticklabels(categorias)
    if escala_pct:
        maximo = 100
        ax.set_ylim(0, 112)
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}%"))
    else:
        maximo = max(max(valores), 1)
        ax.set_ylim(0, maximo * teto)
        ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: fmt_int(v)))
    for i, (valor, cor) in enumerate(zip(valores, cores)):
        _barra_arredondada(ax, i, valor, largura, cor)
        topo = valor + maximo * 0.025
        if sublabels:
            ax.text(i, topo, sublabels[i], ha="center", va="bottom", fontsize=TAM_VALOR_2, color=COR_TEXTO_2, zorder=4)
            topo += maximo * 0.075
        ax.text(i, topo, rotulos[i], ha="center", va="bottom", fontsize=TAM_VALOR,
                fontweight="bold", color=COR_TEXTO, zorder=4)


def _legenda_quadrados(fig, itens, y=0.745):
    """Legenda centralizada (quadradinho de cor + texto), logo abaixo do cabeçalho."""
    larguras = [0.024 + 0.0085 * len(texto) + 0.035 for _, texto in itens]  # quadrado + texto + respiro
    x = 0.5 - (sum(larguras) - 0.035) / 2
    for (cor, texto), largura in zip(itens, larguras):
        fig.add_artist(Rectangle((x, y - 0.012), 0.016, 0.026, transform=fig.transFigure,
                                 facecolor=cor, edgecolor="none"))
        fig.text(x + 0.024, y, texto, ha="left", va="center", fontsize=TAM_EIXO, color=COR_TEXTO_2)
        x += largura


# =====================================================================
# Gráficos genéricos (reaproveitados pelos indicadores)
# =====================================================================
def grafico_contagem_pct(titulo, subtitulo, periodo, categorias, valores, cores, rotulo_y,
                         base_pct=None, nota=None, pasta=PASTA_LOCAL_PADRAO, nome="grafico.png"):
    """Colunas com a contagem em negrito e o percentual (sobre base_pct, ou
    sobre a soma) logo abaixo. Serve para aprovado × reprovado,
    disponível × esperado, convergência × divergência, faixas do 2.2."""
    base = base_pct if base_pct else (sum(valores) or 1)
    fig, ax = _nova_figura(titulo, subtitulo, periodo)
    _colunas(ax, categorias, valores, cores,
             rotulos=[fmt_int(v) for v in valores],
             sublabels=[fmt_pct(v / base * 100) for v in valores])
    _rotulo_eixo_y(ax, rotulo_y)
    _rodape(fig, nota)
    return _salvar(fig, pasta, nome)


def grafico_percentual(titulo, subtitulo, periodo, categorias, valores_pct, cores, rotulo_y,
                       nota=None, pasta=PASTA_LOCAL_PADRAO, nome="grafico.png"):
    """Colunas em % (eixo 0-100)."""
    fig, ax = _nova_figura(titulo, subtitulo, periodo)
    _colunas(ax, categorias, valores_pct, cores, rotulos=[fmt_pct(v) for v in valores_pct], escala_pct=True)
    _rotulo_eixo_y(ax, rotulo_y)
    _rodape(fig, nota)
    return _salvar(fig, pasta, nome)


def grafico_contagem_simples(titulo, subtitulo, periodo, categorias, valores, rotulo_y, cor=AZUL_1,
                             nota=None, pasta=PASTA_LOCAL_PADRAO, nome="grafico.png"):
    """Colunas com o valor no topo (dias da semana, meses). `cor` pode ser
    uma cor só ou uma lista (uma por coluna)."""
    fig, ax = _nova_figura(titulo, subtitulo, periodo)
    cores = list(cor) if isinstance(cor, (list, tuple)) else [cor] * len(valores)
    _colunas(ax, categorias, valores, cores, rotulos=[fmt_int(v) for v in valores],
             largura=0.46 if len(valores) <= 3 else 0.56, teto=1.18)
    _rotulo_eixo_y(ax, rotulo_y)
    _rodape(fig, nota)
    return _salvar(fig, pasta, nome)


def grafico_barras_100(titulo, subtitulo, periodo, linhas, nota=None, pasta=PASTA_LOCAL_PADRAO,
                       nome="grafico.png", rotulos_legenda=("Aprovado", "Reprovado")):
    """Barras horizontais 100% empilhadas (uma por teste), com vão branco
    de 2 px entre os segmentos. `linhas` = [(rótulo, aprovado, reprovado), ...]."""
    n = len(linhas)
    altura_eixo = min(0.13 * n + 0.05, 0.55)
    base_eixo = 0.18 + (0.52 - altura_eixo) / 2
    fig, ax = _nova_figura(titulo, subtitulo, periodo, eixo=[0.30, base_eixo, 0.60, altura_eixo])
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=COR_GRADE, linewidth=0.8)
    ax.spines["bottom"].set_visible(False)
    ax.set_xlim(0, 100)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v)}%"))
    ax.tick_params(axis="x", labelsize=TAM_EIXO - 1.5, colors=COR_TEXTO_3)
    ax.set_yticks([])
    gap = 100 * 2 / (ax.get_window_extent().width or 1)  # 2 px em unidades de %
    for i, (rotulo, aprov, reprov) in enumerate(linhas):
        base = (aprov + reprov) or 1
        p_ap, p_rp = aprov / base * 100, reprov / base * 100
        ax.barh(i, max(p_ap - gap / 2, 0), height=0.52, color=AZUL_1, zorder=3)
        ax.barh(i, max(p_rp - gap / 2, 0), left=p_ap + gap / 2, height=0.52, color=AZUL_3, zorder=3)
        ax.text(-2.5, i - 0.07, rotulo, ha="right", va="center", fontsize=TAM_EIXO + 0.5,
                fontweight="bold", color=COR_TEXTO)
        ax.text(-2.5, i + 0.24, f"{fmt_int(base)} leituras", ha="right", va="center",
                fontsize=TAM_NOTA, color=COR_TEXTO_3)
        if p_ap >= 12:
            ax.text(p_ap / 2, i, fmt_pct(p_ap), ha="center", va="center", fontsize=TAM_VALOR - 1,
                    fontweight="bold", color="#ffffff", zorder=4)
        if p_rp >= 12:
            ax.text(p_ap + p_rp / 2, i, fmt_pct(p_rp), ha="center", va="center", fontsize=TAM_VALOR - 1,
                    fontweight="bold", color=COR_TEXTO, zorder=4)
        elif p_rp > 0:  # segmento estreito demais: valor do lado de fora
            ax.text(101.5, i, fmt_pct(p_rp), ha="left", va="center", fontsize=TAM_VALOR - 2,
                    color=COR_TEXTO_2, zorder=4)
    _legenda_quadrados(fig, [(AZUL_1, rotulos_legenda[0]), (AZUL_3, rotulos_legenda[1])])
    _rodape(fig, nota)
    return _salvar(fig, pasta, nome)


# =====================================================================
# HIDROLOGIA -- 2.1, 2.2, 2.8
# =====================================================================
ROTULOS_FAIXA = [(10, "Ótima\n(10)"), (9, "Muito boa\n(9)"), (8, "Boa\n(8)"), (7, "Regular\n(7)"), (0, "Reprovada\n(0)")]


def _periodo_hidro(dados):
    # dados["periodo"] = "Período: 01/07/2026 a 29/09/2026"
    return dados["periodo"].replace("Período:", "Período considerado:")


def _protegido(funcao, *args, **kwargs):
    """Um gráfico com problema não impede os outros."""
    try:
        return funcao(*args, **kwargs)
    except Exception as erro:  # noqa: BLE001
        print(f"  AVISO: gráfico '{kwargs.get('nome', funcao.__name__)}' não gerado "
              f"({type(erro).__name__}: {erro}).")
        return None


def graficos_hidro(dados, pasta=PASTA_LOCAL_PADRAO):
    """Gera os PNGs de 2.1, 2.2 e 2.8 a partir do `dados` do Contrato de
    Gestão (paginas_hidrologia.gerar_hidro_cg(..., devolver_dados=True))."""
    periodo = _periodo_hidro(dados)
    arquivos = []

    # ---- 2.1 -- atraso na transmissão (universo "com dados") ----
    i21 = dados.get("ind_2_1") or {}
    universos = [u for u in i21.get("universos", []) if u.get("n")]
    if universos:
        u = universos[-1]  # no CG só existe o universo "Com dados"
        arquivos.append(_protegido(
            grafico_percentual,
            "Indicador 2.1 — Atraso na transmissão de dados hidrológicos",
            "Pacotes de dados transmitidos, por situação de atraso",
            f"Período considerado: {i21['periodo']}",
            ["Sem atraso", "Com atraso", "Não recebido"],
            [u["sem_atraso"], u["com_atraso"], u["nao_recebido"]],
            [AZUL_1, AZUL_3, AZUL_4], "Dados transmitidos (% do previsto)",
            nota=f"{u['n']} estações com dados recebidos no período · atraso = mais de 30 min",
            pasta=pasta, nome="relatorio_2_1_atraso_transmissao.png"))
    else:
        print("  AVISO: 2.1 sem dados nesta rodada -- gráfico não gerado.")

    # ---- 2.2 -- distribuição por faixa (cota e chuva) ----
    i22 = dados.get("ind_2_2") or {}
    for chave, nome_var, arquivo in [("cota", "Cota", "relatorio_2_2_disponibilidade_cota.png"),
                                     ("chuva", "Chuva", "relatorio_2_2_disponibilidade_chuva.png")]:
        ranking = i22.get(chave) or []
        if not ranking:
            continue
        contagem = {p: 0 for p, _ in ROTULOS_FAIXA}
        for est in ranking:
            contagem[int(est["pontuacao"]) if int(est["pontuacao"]) in contagem else 0] += 1
        arquivos.append(_protegido(
            grafico_contagem_pct,
            f"Indicador 2.2 — Disponibilidade de dados · {nome_var}",
            "Número de estações por faixa de pontuação do Cálculo de Desempenho",
            periodo,
            [r for _, r in ROTULOS_FAIXA], [contagem[p] for p, _ in ROTULOS_FAIXA], RAMPA_5,
            "Número de estações", base_pct=len(ranking),
            nota=f"{len(ranking)} estações avaliadas",
            pasta=pasta, nome=arquivo))

    # ---- 2.8 -- consistência ----
    i28 = dados.get("ind_2_8")
    if i28:
        barras = {b["chave"]: b for b in i28["barras"] if "chave" in b}
        if not barras:  # compatibilidade: ordem fixa chuva, nivel_range, nivel_final
            barras = dict(zip(["chuva", "nivel_range", "nivel_final"], i28["barras"]))
        titulo_ch = "Indicador 2.8 — Consistência de dados · Chuva"
        titulo_nv = "Indicador 2.8 — Consistência de dados · Nível"
        nota_ch = i28.get("n_estacoes_chuva")
        nota_nv = i28.get("n_estacoes_nivel")
        nota_ch = f"{nota_ch} estações pluviométricas" if nota_ch else None
        nota_nv = f"{nota_nv} estações fluviométricas e pluviométricas" if nota_nv else None

        disp = i28.get("disponibilidade_chuva")
        if disp and disp.get("esperadas"):
            arquivos.append(_protegido(
                grafico_contagem_pct, titulo_ch, "Leituras disponíveis × leituras esperadas", periodo,
                ["Disponíveis", "Esperadas"], [disp["coletadas"], disp["esperadas"]], [AZUL_1, AZUL_4],
                "Nº de leituras", base_pct=disp["esperadas"], nota=nota_ch,
                pasta=pasta, nome="relatorio_2_8_chuva_disponibilidade.png"))

        for chave, titulo, subtitulo, nota, arquivo in [
            ("chuva", titulo_ch, "Teste de valores impossíveis (acumulado mensal)", nota_ch,
             "relatorio_2_8_chuva_consistencia.png"),
            ("nivel_range", titulo_nv, "Teste Range (alcance)", nota_nv, "relatorio_2_8_nivel_range.png"),
            ("nivel_final", titulo_nv, "Teste Persist (resultado final: Range + Persist)", nota_nv,
             "relatorio_2_8_nivel_persist.png"),
        ]:
            b = barras.get(chave)
            if not b or not b.get("base"):
                continue
            arquivos.append(_protegido(
                grafico_contagem_pct, titulo, subtitulo, periodo, ["Aprovado", "Reprovado"],
                [b["aprovado"], b["reprovado"]], [AZUL_1, AZUL_3], "Nº de leituras", base_pct=b["base"],
                nota=nota, pasta=pasta, nome=arquivo))

        linhas = [(rot, barras[c]["aprovado"], barras[c]["reprovado"])
                  for c, rot in [("chuva", "Chuva"), ("nivel_range", "Nível · Range"),
                                 ("nivel_final", "Nível · Persist")] if c in barras and barras[c].get("base")]
        if linhas:
            arquivos.append(_protegido(
                grafico_barras_100, "Indicador 2.8 — Consistência de dados",
                "Percentual de leituras aprovadas e reprovadas, por teste", periodo, linhas,
                nota="Leituras em branco, suspeitas e 'Teste não realizado' contam como reprovadas",
                pasta=pasta, nome="relatorio_2_8_resumo_testes.png"))

    merge = dados.get("merge")
    if merge and (merge["convergencia"] + merge["divergencia"]):
        arquivos.append(_protegido(
            grafico_contagem_pct, "Indicador 2.8 — Consistência de dados · Chuva",
            "Comparação com o satélite MERGE (CPTEC/INPE)",
            "Período considerado: " + merge["periodo"].split(" (")[0],
            ["Convergência", "Divergência"], [merge["convergencia"], merge["divergencia"]], [AZUL_1, AZUL_3],
            "Nº de dias (estação × dia)",
            nota=" ",
            pasta=pasta, nome="relatorio_2_8_chuva_merge.png"))
    elif i28:
        print("  AVISO: comparação com o MERGE indisponível nesta rodada -- gráfico do MERGE não atualizado.")

    return [a for a in arquivos if a]


# =====================================================================
# METEOROLOGIA -- 4.1, 4.2, 4.3
# =====================================================================
def graficos_meteo(dados, pasta=PASTA_LOCAL_PADRAO):
    """Gera os PNGs de 4.1, 4.2 e 4.3 a partir do `dados` do Contrato de
    Gestão (meteorologia_cg.gerar_meteo_cg(..., devolver_dados=True))."""
    periodo = dados["periodo"].replace("Período:", "Período considerado:")
    totais = dados.get("totais", {})
    arquivos = []

    i41 = dados["ind_4_1"]
    dias_completos = {"Seg": "Segunda", "Ter": "Terça", "Qua": "Quarta", "Qui": "Quinta",
                      "Sex": "Sexta", "Sáb": "Sábado", "Dom": "Domingo"}
    t41 = totais.get("4_1", {})
    arquivos.append(_protegido(
        grafico_contagem_simples, "Indicador 4.1 — Previsões do tempo publicadas",
        "Previsões publicadas por dia da semana", periodo,
        [dias_completos.get(d, d) for d, _ in i41["por_dia_semana"]], [n for _, n in i41["por_dia_semana"]],
        "Previsões publicadas",
        nota=(f"{fmt_int(t41['publicadas'])} previsões publicadas de {fmt_int(t41['esperadas'])} esperadas "
              "(1 por dia, incluindo fins de semana e feriados)") if t41 else None,
        pasta=pasta, nome="relatorio_4_1_previsoes_dia_semana.png"))

    t42 = totais.get("4_2")
    if t42:
        arquivos.append(_protegido(
            grafico_contagem_simples,
            "Indicador 4.2 — Monitoramento meteorológico e envio de alertas",
            "Relatórios diários publicados × alertas individuais publicados", periodo,
            ["Relatórios diários", "Alertas individuais"], [t42["relatorios"], t42["alertas"]], "Quantidade",
            cor=[AZUL_1, AZUL_3],
            nota=f"Relatório diário = dia com pelo menos um alerta publicado · {t42['dias_no_periodo']} dias no período",
            pasta=pasta, nome="relatorio_4_2_relatorios_alertas.png"))
    i42 = dados["ind_4_2"]
    if len(i42["por_mes_dias"]) > 1:
        arquivos.append(_protegido(
            grafico_contagem_simples,
            "Indicador 4.2 — Monitoramento meteorológico e envio de alertas",
            "Relatórios diários (dias com alerta) por mês", periodo,
            [m for m, _ in i42["por_mes_dias"]], [n for _, n in i42["por_mes_dias"]], "Relatórios diários",
            pasta=pasta, nome="relatorio_4_2_relatorios_por_mes.png"))

    i43 = dados["ind_4_3"]
    t43 = totais.get("4_3", {})
    arquivos.append(_protegido(
        grafico_contagem_simples, "Indicador 4.3 — Monitoramento climático",
        "Boletins de tendência climática publicados por mês", periodo,
        [m for m, _ in i43["por_mes"]], [n for _, n in i43["por_mes"]], "Boletins publicados",
        nota=(f"{t43['publicados']} boletim(ns) publicado(s) de {t43['esperados']} mês(es) esperado(s)"
              if t43 else None),
        pasta=pasta, nome="relatorio_4_3_boletins_mes.png"))

    return [a for a in arquivos if a]


# =====================================================================
# Drive
# =====================================================================
def pasta_drive_padrao():
    import config_cg
    return os.environ.get("PASTA_GRAFICOS_RELATORIO_ID") or config_cg.PASTA_GRAFICOS_RELATORIO_ID


def publicar_no_drive(servico, caminhos, pasta_id=None):
    """Envia os PNGs ao Drive, SOBRESCREVENDO o arquivo de mesmo nome
    (drive_io.salvar_arquivo mantém o mesmo ID -- links e atalhos continuam
    valendo)."""
    import drive_io
    pasta_id = pasta_id or pasta_drive_padrao()
    enviados = 0
    for caminho in caminhos:
        try:
            drive_io.salvar_arquivo(servico, caminho, os.path.basename(caminho), pasta_id)
            enviados += 1
        except Exception as erro:  # noqa: BLE001
            print(f"  AVISO: não consegui enviar {caminho} ao Drive ({type(erro).__name__}: {erro}).")
    print(f"  {enviados} de {len(caminhos)} gráfico(s) do relatório atualizados no Drive.")
    return enviados


def gerar_e_publicar_hidro(dados, servico=None, pasta=PASTA_LOCAL_PADRAO):
    print("\n--- Gráficos do relatório (2.1, 2.2, 2.8) ---")
    caminhos = graficos_hidro(dados, pasta)
    if servico is not None:
        publicar_no_drive(servico, caminhos)
    return caminhos


def gerar_e_publicar_meteo(dados, servico=None, pasta=PASTA_LOCAL_PADRAO):
    print("\n--- Gráficos do relatório (4.1, 4.2, 4.3) ---")
    caminhos = graficos_meteo(dados, pasta)
    if servico is not None:
        publicar_no_drive(servico, caminhos)
    return caminhos


# =====================================================================
# Uso manual
# =====================================================================
def dados_exemplo():
    """Dados de EXEMPLO (formato real, números do relatório de 25/09/2026)
    -- só para ver o desenho sem acessar o Drive (--exemplo)."""
    ranking = lambda pts: [{"codigo": str(i), "nome": "", "percentual": 0, "pontuacao": p} for i, p in enumerate(pts)]
    hidro = {
        "periodo": "Período: 01/07/2026 a 25/09/2026",
        "ind_2_1": {"periodo": "11/08/2026 a 25/09/2026", "universos": [
            {"rotulo": "Com dados (50)", "n": 50, "nota": 0, "sem_atraso": 67.5, "com_atraso": 1.9, "nao_recebido": 30.6}]},
        "ind_2_2": {"cota": ranking([10] * 19 + [9] * 2 + [8] * 3 + [7] * 4 + [0] * 35),
                    "chuva": ranking([10] * 30 + [9] * 2 + [8] * 3 + [7] * 3 + [0] * 28)},
        "ind_2_8": {"barras": [
            {"chave": "chuva", "rotulo": "Chuva", "aprovado": 334854, "reprovado": 5143, "base": 339997},
            {"chave": "nivel_range", "rotulo": "Range", "aprovado": 221663, "reprovado": 95025, "base": 316688},
            {"chave": "nivel_final", "rotulo": "Persist", "aprovado": 174952, "reprovado": 141736, "base": 316688}],
            "disponibilidade_chuva": {"coletadas": 334854, "esperadas": 339997},
            "n_estacoes_chuva": 55, "n_estacoes_nivel": 44},
        "merge": {"convergencia": 3907, "divergencia": 199, "periodo": "01/07/2026 a 28/09/2026 (último dia)"},
    }
    meteo = {
        "periodo": "Período: 16/09/2026 a 25/09/2026",
        "ind_4_1": {"por_dia_semana": [("Seg", 1), ("Ter", 1), ("Qua", 2), ("Qui", 2), ("Sex", 2), ("Sáb", 1), ("Dom", 1)]},
        "ind_4_2": {"por_mes_dias": [("Set/26", 8)], "por_mes_alertas": [("Set/26", 94)]},
        "ind_4_3": {"por_mes": [("Set/26", 1)]},
        "totais": {"4_1": {"publicadas": 10, "esperadas": 10},
                   "4_2": {"relatorios": 8, "alertas": 94, "dias_no_periodo": 10},
                   "4_3": {"publicados": 1, "esperados": 1}},
    }
    return hidro, meteo


def _dados_hidro_do_drive(servico):
    """Monta o `dados` do CG com as MESMAS entradas do rodar_diario_hidro
    (lê tudo do Drive; nada é gravado). Gera a página numa pasta temporária."""
    import tempfile

    import config
    import config_cg
    import drive_io
    import indicador_2_1_calculo
    import indicador_2_8_calculo
    import paginas_hidrologia

    config_cg.carregar_exclusoes_do_drive(servico)
    fato = drive_io.ler_csv(servico, "fato_disponibilidade.csv", config.PASTA_RELATORIOS_ID)
    dim = drive_io.ler_csv(servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID)
    try:
        pacotes = indicador_2_1_calculo.carregar_pacotes_telemetria_detalhada(servico, config.PASTA_TELEMETRIA_DETALHADA_ID)
    except RuntimeError as erro:
        print(f"AVISO: {erro} -- 2.1 sem dado.")
        pacotes = None
    resumo = drive_io.ler_csv(servico, indicador_2_8_calculo.NOME_RESUMO, config.PASTA_RELATORIOS_ID)
    with tempfile.TemporaryDirectory() as tmp:
        _, dados = paginas_hidrologia.gerar_hidro_cg(fato, dim, pacotes, resumo, os.path.join(tmp, "cg.html"),
                                                     devolver_dados=True)
    return dados


def _dados_meteo_do_simge():
    import tempfile

    import meteorologia_cg
    with tempfile.TemporaryDirectory() as tmp:
        _, dados = meteorologia_cg.gerar_meteo_cg(os.path.join(tmp, "cg.html"), devolver_dados=True)
    return dados


def main():
    parser = argparse.ArgumentParser(description="Gera os gráficos do relatório mensal (Contrato de Gestão).")
    parser.add_argument("--saida", default=PASTA_LOCAL_PADRAO, help="pasta local dos PNGs")
    parser.add_argument("--so-local", action="store_true", help="não envia ao Drive")
    parser.add_argument("--exemplo", action="store_true", help="usa dados de exemplo (não acessa Drive/SIMGE)")
    parser.add_argument("--apenas", choices=["hidro", "meteo"], help="gera só um dos grupos")
    parser.add_argument("--chave", default=os.environ.get("CAMINHO_CHAVE_JSON", "chave_servico.json"))
    args = parser.parse_args()

    if args.exemplo:
        hidro, meteo = dados_exemplo()
        if args.apenas != "meteo":
            graficos_hidro(hidro, args.saida)
        if args.apenas != "hidro":
            graficos_meteo(meteo, args.saida)
        return

    import drive_io
    servico = drive_io.conectar_drive(args.chave)
    destino = None if args.so_local else servico
    if args.apenas != "meteo":
        gerar_e_publicar_hidro(_dados_hidro_do_drive(servico), destino, args.saida)
    if args.apenas != "hidro":
        gerar_e_publicar_meteo(_dados_meteo_do_simge(), destino, args.saida)


if __name__ == "__main__":
    main()
