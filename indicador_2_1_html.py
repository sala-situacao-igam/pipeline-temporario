"""
Descrição: monta o cartão HTML do indicador 2.1 (atraso na transmissão de
dados hidrológicos), nos dois universos de estação (64 e 44), no MESMO
padrão visual do indicador_meteorologia.py (cartão com pontuação em
destaque -- estilo "hero-valor" -- acima dos gráficos, gráfico de barras
verticais em CSS puro, mesma paleta/fonte de todo o site).

Este módulo só devolve o HTML do cartão (uma string) -- não gera uma
página inteira sozinho. Quem gera a página é indicador_2_2_html.gerar_html_2_2(),
que recebe esse cartão pronto e o insere ACIMA do cartão do indicador 2.2
(mesma página, index.html/hidrometria).

Conexões do Pipeline:
- Entradas: os 2 dicionários de resultado_cd de
  indicador_2_1_calculo.calcular_cd_2_1 (um por universo) e o texto do
  período (ver docstring de indicador_2_1_calculo.py).
- Saídas: string HTML (cartao_2_1_html), passada para
  indicador_2_2_html.gerar_html_2_2(..., cartao_2_1_html=...).

Funções:
- gerar_cartao_2_1_html: monta o cartão completo (título, período, os 2
  painéis lado a lado).

Uso (Colab):
    from indicador_2_1_calculo import calcular_cd_2_1  # ver esboço/calculo p/ carregar os dados
    from indicador_2_1_html import gerar_cartao_2_1_html
    from indicador_2_2_html import gerar_html_2_2

    cartao_2_1_html = gerar_cartao_2_1_html(resultado_64, resultado_44, periodo_texto)
    gerar_html_2_2(df_pontuacao, "index.html", cartao_2_1_html=cartao_2_1_html)
"""
import html as _html

# Importa de indicador_2_1_calculo.py (não de exportar_imagem_indicador_2_1.py)
# DE PROPÓSITO: esse módulo não usa matplotlib, e este arquivo é importado
# todo dia por rodar_diario_hidro.py (Fase 5), que só gera HTML/CSS -- sem
# nenhum PNG. Importar de exportar_imagem_indicador_2_1 aqui foi o que
# quebrou a primeira rodada real do Actions em 09/09
# (ModuleNotFoundError: matplotlib, que só está instalado no Colab).
from indicador_2_1_calculo import (
    COR_SEM_ATRASO,
    COR_COM_ATRASO,
    COR_NAO_RECEBIDO,
    LEGENDA_64,
    LEGENDA_44,
)


def _grafico_barras_2_1_html(resultado, altura_px=170):
    """Gráfico de barras verticais em CSS puro (mesma classe/estilo de
    _grafico_barras_verticais_html em indicador_meteorologia.py), com as 3
    categorias do indicador 2.1 (Sem atraso / Com atraso / Não recebido),
    sempre em % do total previsto -- por isso a escala é fixa (0-100),
    igual ao eixo Y do PNG exportado, e não muda de painel pra painel."""
    total_previsto = resultado["total_previsto"] or 1
    categorias = [
        ("Sem atraso", resultado["recebido_sem_atraso"], COR_SEM_ATRASO),
        ("Com atraso", resultado["recebido_com_atraso"], COR_COM_ATRASO),
        ("Não recebido", resultado["nao_recebido"], COR_NAO_RECEBIDO),
    ]
    colunas_html = "".join(
        f"""
          <div class="barra-vert-item">
            <span class="barra-vert-valor">{f"{(valor / total_previsto * 100):.1f}".replace(".", ",")}%</span>
            <span class="barra-vert-coluna" style="height:{max(2, round(valor / total_previsto * 100))}%; background:{cor};"></span>
            <span class="barra-vert-rotulo">{_html.escape(rotulo)}</span>
          </div>"""
        for rotulo, valor, cor in categorias
    )
    return f"""
        <div class="grafico-barras-vertical" style="height:{altura_px}px;">{colunas_html}
        </div>"""


def _painel_2_1_html(resultado, legenda):
    """Uma coluna do cartão (um universo de estação): pontuação (CD) em
    destaque igual ao bloco "relatorio-cd" das outras páginas, seguida do
    gráfico de barras e da legenda em cinza (mesmo texto usado no PNG)."""
    percentual_fmt = f"{resultado['resultado_pct']:.2f}".replace(".", ",")
    grafico_html = _grafico_barras_2_1_html(resultado)
    return f"""
        <div>
          <p class="hero-label">Pontuação (Cálculo de Desempenho) — {resultado['n_estacoes']} estações</p>
          <div class="hero-valor hero-valor--compacto">{resultado['cd']} <small>/ 10</small></div>
          <p class="hero-secundario">
            {percentual_fmt}% sem atraso
            — <span class="valor-secundario">{resultado['recebido_sem_atraso']} pacotes sem atraso de {resultado['total_previsto']} previstos</span>
          </p>
          <div style="margin-top:14px;">
            {grafico_html}
          </div>
          <p class="legenda-grafico">{_html.escape(legenda)}</p>
        </div>"""


def gerar_cartao_2_1_html(resultado_64, resultado_44, periodo_texto=None):
    """Monta o cartão completo do indicador 2.1: título, período (opcional,
    em cinza, mesmo estilo do subtítulo dos outros cartões) e os 2 painéis
    (64 e 44 estações) lado a lado -- mesmo grid de 2 colunas usado no
    cartão do indicador 4.2 (grid-duas-colunas), com pontuação + gráfico em
    cada coluna em vez de "total de relatórios..."."""
    subtitulo_html = (
        f'<p class="subtitulo-cartao">{_html.escape(periodo_texto)}</p>' if periodo_texto else ""
    )
    return f"""
    <div class="cartao">
      <h2>2.1 — Atraso na transmissão de dados hidrológicos</h2>
      {subtitulo_html}
      <div class="grid-duas-colunas">{_painel_2_1_html(resultado_64, LEGENDA_64)}{_painel_2_1_html(resultado_44, LEGENDA_44)}
      </div>
    </div>
"""
