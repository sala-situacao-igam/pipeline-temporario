"""
Descrição: exporta o indicador 2.1 (atraso na transmissão de dados
hidrológicos) como imagem PNG, comparando os dois universos de estação
lado a lado (64 estações, mesmo escopo do indicador 2.2, vs 44 estações
com dado retornado pela API nova no intervalo considerado) -- mesmo layout
de comparação usado no indicador 4.2 do dashboard de meteorologia.

Conexões do Pipeline:
- Entradas: dicionários de resultado_cd de indicador_2_1_calculo.calcular_cd_2_1
  (um pra cada universo) e o texto do período (intervalo de datas coberto
  pelos dados usados no cálculo).
- Saídas: PNG salvo localmente, enviado ao Drive (config.PASTA_GRAFICOS_ID)
  por gerar_relatorios_visuais.py (script manual do Colab -- o pipeline
  automático diário, rodar_diario_hidro.py, NÃO chama este módulo: o
  cartão do 2.1 dentro do hidrometria.html é gerado em CSS puro por
  indicador_2_1_html.py, sem precisar de matplotlib).

Funções:
- exportar_comparacao_2_1: gera o gráfico de barras comparando os dois
  universos (64 x 44) em PNG.

Uso (Colab):
    import config, drive_io
    from indicador_2_1_calculo import (
        carregar_universo_64, carregar_pacotes_telemetria_detalhada, calcular_cd_2_1,
    )
    from exportar_imagem_indicador_2_1 import exportar_comparacao_2_1

    servico = drive_io.conectar_drive("CHAVE.json")
    estacoes_64 = carregar_universo_64(servico)
    df_pacotes = carregar_pacotes_telemetria_detalhada(servico, config.PASTA_TELEMETRIA_DETALHADA_ID)
    estacoes_44 = sorted(df_pacotes["codigo_estacao"].unique().tolist())

    resultado_64 = calcular_cd_2_1(df_pacotes, estacoes_64, dias_periodo=30)
    resultado_44 = calcular_cd_2_1(df_pacotes, estacoes_44, dias_periodo=30)

    periodo_texto = (
        f"Período considerado: {df_pacotes['Data_Hora_Medicao'].min():%d/%m/%Y} "
        f"a {df_pacotes['Data_Hora_Medicao'].max():%d/%m/%Y}"
    )

    exportar_comparacao_2_1(resultado_64, resultado_44, periodo_texto, "indicador_2_1_comparacao_64_44.png")
"""
import matplotlib.pyplot as plt

# Cores e legendas moram em indicador_2_1_calculo.py (módulo sem matplotlib)
# e são só reaproveitadas aqui -- ver comentário lá pra saber o porquê.
from indicador_2_1_calculo import (
    COR_SEM_ATRASO,
    COR_COM_ATRASO,
    COR_NAO_RECEBIDO,
    LEGENDA_64,
    LEGENDA_44,
)

COR_FUNDO = "#fcfcfb"
COR_TEXTO = "#0b0b0b"
COR_TEXTO_SECUNDARIO = "#52514e"
COR_BORDA = "#e1e0d9"

TITULO_COMPARACAO_2_1 = "Indicador 2.1 — Atraso na transmissão de dados hidrológicos"


def _plotar_painel(ax, resultado, legenda):
    """Desenha as 3 barras verticais (sem atraso / com atraso / não
    recebido, em % do total previsto) de um único painel, com o CD e o
    Resultado% acima."""
    total_previsto = resultado["total_previsto"] or 1
    valores_pct = [
        resultado["recebido_sem_atraso"] / total_previsto * 100,
        resultado["recebido_com_atraso"] / total_previsto * 100,
        resultado["nao_recebido"] / total_previsto * 100,
    ]
    categorias = ["Sem atraso", "Com atraso", "Não recebido"]
    cores = [COR_SEM_ATRASO, COR_COM_ATRASO, COR_NAO_RECEBIDO]

    barras = ax.bar(categorias, valores_pct, color=cores, width=0.6)
    for retangulo, valor in zip(barras, valores_pct):
        ax.text(
            retangulo.get_x() + retangulo.get_width() / 2, retangulo.get_height() + 1.5,
            f"{valor:.1f}%", ha="center", va="bottom", fontsize=9, fontweight="bold", color=COR_TEXTO,
        )

    ax.set_title(
        f"CD: {resultado['cd']}/10   |   Resultado: {resultado['resultado_pct']:.2f}%",
        fontsize=11, fontweight="bold", color=COR_TEXTO, pad=12,
    )
    ax.set_ylim(0, 100)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.spines["bottom"].set_color(COR_BORDA)
    ax.tick_params(axis="x", labelsize=9, colors=COR_TEXTO_SECUNDARIO, length=0)
    ax.tick_params(axis="y", labelsize=8, colors=COR_TEXTO_SECUNDARIO)
    ax.yaxis.grid(True, color=COR_BORDA, linewidth=0.7)
    ax.set_axisbelow(True)

    ax.text(
        0.5, -0.18, legenda, transform=ax.transAxes, ha="center", va="top",
        fontsize=8, color=COR_TEXTO_SECUNDARIO, wrap=True,
    )


def exportar_comparacao_2_1(
    resultado_64,
    resultado_44,
    periodo_texto=None,
    caminho_saida="indicador_2_1_comparacao_64_44.png",
    dpi=200,
    titulo=TITULO_COMPARACAO_2_1,
):
    """Gera o PNG com os 2 painéis lado a lado (64 estações x 44 estações).
    Só o painel esquerdo recebe o rótulo do eixo Y ("Dados transmitidos
    (%)"), já que os dois compartilham a mesma escala. `periodo_texto`,
    quando informado, aparece em cinza logo abaixo do título, e deve ser
    recalculado a cada rodada a partir do intervalo real dos dados usados
    (min/max de Data_Hora_Medicao em df_pacotes)."""
    fig, (ax_esquerda, ax_direita) = plt.subplots(1, 2, figsize=(11, 5.5), dpi=dpi, sharey=True)
    fig.patch.set_facecolor(COR_FUNDO)

    for eixo in (ax_esquerda, ax_direita):
        eixo.set_facecolor(COR_FUNDO)

    _plotar_painel(ax_esquerda, resultado_64, LEGENDA_64)
    _plotar_painel(ax_direita, resultado_44, LEGENDA_44)

    ax_esquerda.set_ylabel("Dados transmitidos (%)", fontsize=9, color=COR_TEXTO_SECUNDARIO)

    if titulo:
        fig.suptitle(titulo, fontsize=13, color=COR_TEXTO, y=1.06)
    if periodo_texto:
        fig.text(0.5, 0.98, periodo_texto, ha="center", fontsize=9, color=COR_TEXTO_SECUNDARIO)

    fig.savefig(caminho_saida, facecolor=COR_FUNDO, bbox_inches="tight")
    print(f"Imagem salva em: {caminho_saida}")
    return caminho_saida
