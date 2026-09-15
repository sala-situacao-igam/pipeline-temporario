"""
Descrição: exporta o indicador 2.2 (distribuição de pontuação por faixa)
como imagem PNG, pronta para entrar num relatório.

Conexões do Pipeline:
- Entradas: DataFrame de pontuação de indicador_2_2_calculo.py.
- Saídas: PNG salvo localmente, enviado ao Drive (config.PASTA_GRAFICOS_ID)
  por gerar_relatorios_visuais.py.

Funções:
- exportar_barras_faixa_2_2: gera o gráfico de barras por faixa de pontuação em PNG.

Uso (Colab):
    import config, drive_io
    from indicador_2_2_calculo import calcular_pontuacao_2_2
    from exportar_imagem_indicador_2_2 import exportar_barras_faixa_2_2

    servico = drive_io.conectar_drive("CHAVE.json")
    fato_disponibilidade = drive_io.ler_csv(servico, "fato_disponibilidade.csv", config.PASTA_RELATORIOS_ID)
    dim_estacao = drive_io.ler_csv(servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID)
    df_pontuacao = calcular_pontuacao_2_2(fato_disponibilidade, dim_estacao)

    exportar_barras_faixa_2_2(df_pontuacao, "indicador_2_2_barras_faixa.png")
"""
import matplotlib.pyplot as plt
import numpy as np

from indicador_2_2_calculo import (
    ORDEM_PONTUACAO,
    ROTULO_PONTUACAO,
    distribuicao_pontuacao,
)

COR_FUNDO = "#fcfcfb"
COR_TEXTO = "#0b0b0b"
COR_TEXTO_SECUNDARIO = "#52514e"
COR_BORDA = "#e1e0d9"
COR_BARRA_FAIXA_2_2 = "#1c3f66"  

TITULO_BARRAS_FAIXA_2_2 = (
    "Indicador 2.2 — Percentual de transmissão de dados hidrológicos sem perda de registros\n"
    "Número de estações por categoria de pontuação do Cálculo de Desempenho"
)


def exportar_barras_faixa_2_2(
    df_pontuacao,
    caminho_saida="indicador_2_2_barras_faixa.png",
    dpi=200,
    titulo=TITULO_BARRAS_FAIXA_2_2,
):
    """Barras verticais: eixo X = faixa de pontuação (Ótima...Reprovada),
    eixo Y = nº de estações naquela faixa (sem legenda separada, as
    categorias já ficam identificadas no eixo X). Todas as barras numa
    única cor (COR_BARRA_FAIXA_2_2); rótulo de cada barra mostra a
    contagem absoluta e o percentual em relação ao total de estações (ex.:
    "32 (50%)"). Passe `titulo=None` para gerar sem título embutido."""
    distrib = distribuicao_pontuacao(df_pontuacao)
    categorias = [ROTULO_PONTUACAO[p] for p in ORDEM_PONTUACAO]
    valores = [int(distrib[p]) for p in ORDEM_PONTUACAO]
    total_estacoes = sum(valores) if sum(valores) > 0 else 1
    maximo = max(valores) if max(valores) > 0 else 1

    fig, ax = plt.subplots(figsize=(7, 4.5), dpi=dpi)
    fig.patch.set_facecolor(COR_FUNDO)
    ax.set_facecolor(COR_FUNDO)

    x = np.arange(len(categorias))
    barras = ax.bar(x, valores, color=COR_BARRA_FAIXA_2_2, width=0.6)

    for retangulo, valor in zip(barras, valores):
        percentual = round(valor / total_estacoes * 100)
        ax.text(
            retangulo.get_x() + retangulo.get_width() / 2, retangulo.get_height() + maximo * 0.02,
            f"{valor} ({percentual}%)", ha="center", va="bottom", fontsize=10, fontweight="bold", color=COR_TEXTO,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(categorias, fontsize=9, color=COR_TEXTO_SECUNDARIO)
    ax.set_xlabel("Pontuação do Cálculo de Desempenho", fontsize=9, color=COR_TEXTO_SECUNDARIO)
    ax.set_ylabel("Número de Estações", fontsize=9, color=COR_TEXTO_SECUNDARIO)
    ax.set_ylim(0, maximo * 1.18)
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
