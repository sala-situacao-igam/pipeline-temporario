"""
Descrição: gera o HTML autocontido (CSS/JS embutidos) da página
"Meteorologia" do site (indicadores 4.1, 4.2 e 4.3 -- SIMGE), no mesmo
estilo visual da página do indicador 2.2 (indicador_2_2_html.py).

Conexões do Pipeline:
- Entradas: resultados de extrair_documentos_simge_calculo.py
  (contar_previsoes_4_1, contar_tendencia_climatica_4_3, contar_alertas_4_2,
  calcular_cd_4_1/4_2/4_3).
- Saídas: meteorologia.html, publicado no site (dashboard-igam) via
  rodar_diario_meteoro.py/gerar_relatorios_visuais.py, depois passa por
  nav_site.injetar_nav().

Funções:
- _rotulo_mes: converte "AAAA-MM" em rótulo abreviado, ex. "Mai/2026".
- _grafico_barras_verticais_html: monta um gráfico de barras verticais em CSS puro.
- _grafico_barras_horizontais_html: monta um gráfico de barras horizontais em CSS puro.
- _relatorio_cd_4_1_html: monta o bloco de pontuação (CD) do indicador 4.1.
- _relatorio_cd_4_3_html: monta o bloco de pontuação (CD) do indicador 4.3.
- _relatorio_cd_4_2_html: monta o bloco de pontuação (CD) do indicador 4.2.
- gerar_html_meteorologia: monta o HTML completo da página e grava em disco.

Uso:
    from extrair_documentos_simge_calculo import (
        contar_previsoes_4_1, contar_tendencia_climatica_4_3, contar_alertas_4_2,
        calcular_cd_4_1, calcular_cd_4_3,
    )
    from indicador_meteorologia import gerar_html_meteorologia
    from nav_site import injetar_nav

    data_inicio, data_fim = "2026-01-01", "2026-08-31"
    r_4_1 = contar_previsoes_4_1(URL_PASTA_PREVISOES_2026, data_inicio, data_fim)
    r_4_3 = contar_tendencia_climatica_4_3(URL_PASTA_TENDENCIA_CLIMATICA_2026, data_inicio, data_fim)
    r_4_2 = contar_alertas_4_2(URL_ALERTAS_TEMPESTADE_SEVERA, data_inicio, data_fim)
    cd_4_1 = calcular_cd_4_1(r_4_1, data_inicio, data_fim)
    cd_4_3 = calcular_cd_4_3(r_4_3, data_inicio, data_fim)

    gerar_html_meteorologia(
        r_4_1, r_4_3, "meteorologia.html",
        resultado_cd_4_1=cd_4_1, resultado_cd_4_3=cd_4_3, resultado_4_2=r_4_2,
    )
    injetar_nav("meteorologia.html", "meteorologia")
    # e, quando for publicar de verdade, rodar injetar_nav também no
    # hidrometria.html gerado por gerar_html_2_2() -- ver checklist.
"""
import html as _html
import json as _json

DIAS_SEMANA_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

MESES_PT_ABREV = {
    "01": "Jan", "02": "Fev", "03": "Mar", "04": "Abr",
    "05": "Mai", "06": "Jun", "07": "Jul", "08": "Ago",
    "09": "Set", "10": "Out", "11": "Nov", "12": "Dez",
}


def _rotulo_mes(chave_ano_mes):
    """'2026-05' -> 'Mai/2026'."""
    ano, mes = chave_ano_mes.split("-")
    return f"{MESES_PT_ABREV.get(mes, mes)}/{ano}"


COR_BARRA_4_1 = "#1c3f66"
COR_BARRA_4_3 = "#1c3f66"
COR_BARRA_4_2 = "#1c3f66"


def _grafico_barras_verticais_html(itens, cor, altura_px=170):
    """Gráfico de barras verticais em CSS puro (sem lib/JS), no mesmo
    estilo dos PNGs (exportar_imagem_indicador_2_2.py /
    exportar_imagem_indicador_meteorologia.py) -- valor em cima da barra,
    1 cor sólida, rótulo embaixo. `itens` é uma lista de (rotulo, valor)."""
    maximo = max((valor for _r, valor in itens), default=0) or 1
    colunas_html = "".join(
        f"""
          <div class="barra-vert-item">
            <span class="barra-vert-valor">{valor}</span>
            <span class="barra-vert-coluna" style="height:{max(2, round(valor / maximo * 100))}%; background:{cor};"></span>
            <span class="barra-vert-rotulo">{_html.escape(str(rotulo))}</span>
          </div>"""
        for rotulo, valor in itens
    )
    return f"""
        <div class="grafico-barras-vertical" style="height:{altura_px}px;">{colunas_html}
        </div>"""


def _grafico_barras_horizontais_html(itens, cor):
    """Gráfico de barras horizontais em CSS puro (sem lib/JS) -- 1 linha
    por categoria, rótulo à esquerda, valor à direita da barra. Usado no
    4.2, onde os 12 meses aparecem lado a lado com outro gráfico na mesma
    linha -- com menos largura disponível, barra vertical com 12
    categorias ficaria ilegível. `itens` é uma lista de (rotulo, valor)."""
    maximo = max((valor for _r, valor in itens), default=0) or 1
    linhas_html = "".join(
        f"""
          <div class="barra-horiz-item">
            <span class="barra-horiz-rotulo">{_html.escape(str(rotulo))}</span>
            <span class="barra-horiz-trilha">
              <span class="barra-horiz-barra" style="width:{max(2, round(valor / maximo * 100))}%; background:{cor};"></span>
            </span>
            <span class="barra-horiz-valor">{valor}</span>
          </div>"""
        for rotulo, valor in itens
    )
    return f"""
        <div class="grafico-barras-horizontal">{linhas_html}
        </div>"""


def _relatorio_cd_4_1_html(resultado_cd_4_1):
    """Bloco 'relatório' do CD do 4.1 (dias úteis, previsões publicadas,
    percentual, pontuação, feriados/facultativos descontados do período),
    exibido antes do gráfico de barras. `resultado_cd_4_1` é o dicionário
    devolvido por calcular_cd_4_1() (extrair_documentos_simge_calculo.py)."""
    feriados = resultado_cd_4_1["feriados_no_periodo"]
    linhas_feriados = "".join(
        f"""
        <tr>
          <td>{f['data']:%d/%m/%Y}</td>
          <td>{_html.escape(f['tipo'])}</td>
          <td>{_html.escape(f['rotulo'])}</td>
        </tr>"""
        for f in feriados
    )
    tabela_feriados_html = (
        f"""
      <details class="tabela-acessivel">
        <summary>Ver feriados/pontos facultativos descontados do período ({len(feriados)})</summary>
        <table>
          <thead><tr><th>Data</th><th>Tipo</th><th>Nome</th></tr></thead>
          <tbody>{linhas_feriados}
          </tbody>
        </table>
      </details>"""
        if feriados
        else ""
    )
    return f"""
      <div class="relatorio-cd">
        <p class="hero-label">Pontuação (Cálculo de Desempenho) do período</p>
        <div class="hero-valor">{resultado_cd_4_1['pontuacao']} <small>/ 10</small></div>
        <p class="hero-secundario">
          {resultado_cd_4_1['percentual']}% de transmissão
          — <span class="valor-secundario">{resultado_cd_4_1['previsoes_publicadas']} previsões publicadas de {resultado_cd_4_1['dias_uteis']} dias úteis esperados</span>
        </p>
        {tabela_feriados_html}
      </div>"""


def _relatorio_cd_4_3_html(resultado_cd_4_3):
    """Bloco 'relatório' do CD do 4.3 (meses esperados, boletins
    publicados, percentual, pontuação), exibido antes do gráfico de
    barras, no mesmo padrão do bloco do 4.1. `resultado_cd_4_3` é o
    dicionário devolvido por calcular_cd_4_3()
    (extrair_documentos_simge_calculo.py)."""
    return f"""
      <div class="relatorio-cd">
        <p class="hero-label">Pontuação (Cálculo de Desempenho) do período</p>
        <div class="hero-valor">{resultado_cd_4_3['pontuacao']} <small>/ 10</small></div>
        <p class="hero-secundario">
          {resultado_cd_4_3['percentual']}% de publicação
          — <span class="valor-secundario">{resultado_cd_4_3['boletins_publicados']} boletins publicados de {resultado_cd_4_3['meses_esperados']} meses esperados</span>
        </p>
      </div>"""


def _relatorio_cd_4_2_html(resultado_cd_4_2):
    """Bloco 'relatório' do CD do 4.2 (dias no período, relatórios
    diários emitidos, percentual, pontuação), mesmo padrão dos blocos do
    4.1/4.3, exibido antes dos 2 gráficos do card. `resultado_cd_4_2` é o
    dicionário devolvido por calcular_cd_4_2() (extrair_documentos_simge_calculo.py)."""
    return f"""
      <div class="relatorio-cd">
        <p class="hero-label">Pontuação (Cálculo de Desempenho) do período</p>
        <div class="hero-valor">{resultado_cd_4_2['pontuacao']} <small>/ 10</small></div>
        <p class="hero-secundario">
          {resultado_cd_4_2['percentual']}% de monitoramento
          — <span class="valor-secundario">{resultado_cd_4_2['relatorios_emitidos']} relatórios diários emitidos de {resultado_cd_4_2['dias_no_periodo']} dias no período</span>
        </p>
      </div>"""


def gerar_html_meteorologia(
    resultado_4_1, resultado_4_3, caminho_saida,
    resultado_cd_4_1=None, resultado_cd_4_3=None, resultado_4_2=None,
    resultado_cd_4_2=None,
):
    """Gera o HTML autocontido da página de Meteorologia.

    `resultado_4_1`: devolvido por contar_previsoes_4_1() (extrair_documentos_simge_calculo.py).
    `resultado_4_3`: devolvido por contar_tendencia_climatica_4_3() (idem).
    `resultado_cd_4_1` (opcional): devolvido por calcular_cd_4_1() (idem) --
    quando informado, mostra o bloco de pontuação (CD) do 4.1 antes do
    gráfico de barras. Se None (padrão), o bloco não aparece.
    `resultado_cd_4_3` (opcional): devolvido por calcular_cd_4_3() (idem) --
    mesma ideia do resultado_cd_4_1, para o card do 4.3.
    `resultado_4_2` (opcional): devolvido por contar_alertas_4_2() (idem) --
    quando informado, mostra o card do indicador 4.2 (2 gráficos de
    barras horizontais lado a lado, por mês). Se None (padrão), o card
    não aparece.
    `resultado_cd_4_2` (opcional): devolvido por calcular_cd_4_2() (idem) --
    mostra o bloco de pontuação (CD) do 4.2 antes dos 2 gráficos do card.
    Só tem efeito se `resultado_4_2` também for informado.
    """
    # -- 4.1: barras verticais por dia da semana 
    por_dia_semana = resultado_4_1["por_dia_semana"]
    barras_dia_semana_html = _grafico_barras_verticais_html(
        [(dia, por_dia_semana.get(dia, 0)) for dia in DIAS_SEMANA_PT], COR_BARRA_4_1
    )

    total_4_1 = resultado_4_1["total_arquivos"]
    relatorio_cd_4_1_html = _relatorio_cd_4_1_html(resultado_cd_4_1) if resultado_cd_4_1 else ""

    # -- 4.2: 2 gráficos de barras horizontais lado a lado,
    # por mês (Jan-Dez, zero-fill -- ver contar_alertas_4_2()). --
    cartao_4_2_html = ""
    if resultado_4_2:
        por_mes_dias_4_2 = resultado_4_2["por_mes_dias"]
        por_mes_alertas_4_2 = resultado_4_2["por_mes_alertas"]
        meses_ordenados_4_2 = sorted(por_mes_dias_4_2.keys())
        barras_dias_alerta_html = _grafico_barras_horizontais_html(
            [(_rotulo_mes(m), por_mes_dias_4_2[m]) for m in meses_ordenados_4_2], COR_BARRA_4_2
        )
        barras_alertas_individuais_html = _grafico_barras_horizontais_html(
            [(_rotulo_mes(m), por_mes_alertas_4_2[m]) for m in meses_ordenados_4_2], COR_BARRA_4_2
        )
        relatorio_cd_4_2_html = _relatorio_cd_4_2_html(resultado_cd_4_2) if resultado_cd_4_2 else ""
        cartao_4_2_html = f"""
    <div class="cartao">
      <h2>4.2 — Monitoramento Meteorológico e envio de alertas realizado</h2>
      {relatorio_cd_4_2_html}
      <div class="grid-duas-colunas">
        <div>
          <p class="hero-label">Total de relatórios diários publicados no período</p>
          <div class="hero-valor">{resultado_4_2['total_dias_com_alerta']}</div>
          <div style="margin-top:14px;">
            {barras_dias_alerta_html}
          </div>
        </div>
        <div>
          <p class="hero-label">Total de alertas individuais publicados no período</p>
          <div class="hero-valor">{resultado_4_2['total_alertas_individuais']}</div>
          <div style="margin-top:14px;">
            {barras_alertas_individuais_html}
          </div>
        </div>
      </div>
    </div>
"""

    # -- 4.3: barras verticais por mês de criação real, + tabela dos boletins.
    por_mes = resultado_4_3["por_mes"]
    meses_ordenados = sorted(por_mes.keys())
    barras_mes_html = _grafico_barras_verticais_html(
        [(_rotulo_mes(m), por_mes[m]) for m in meses_ordenados], COR_BARRA_4_3
    )

    total_4_3 = resultado_4_3["total_boletins"]
    relatorio_cd_4_3_html = _relatorio_cd_4_3_html(resultado_cd_4_3) if resultado_cd_4_3 else ""

    linhas_tabela_4_3 = "".join(
        f"""
        <tr>
          <td>{dt:%d/%m/%Y %H:%M}</td>
          <td>{_html.escape(titulo)}</td>
        </tr>"""
        for dt, titulo in resultado_4_3["boletins"]
    )

    pagina = f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Meteorologia — Indicadores 4.1, 4.2 e 4.3</title>
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1:      #fcfcfb;
    --page-plano:     #f9f9f7;
    --text-primary:   #0b0b0b;
    --text-secondary: #52514e;
    --text-muted:     #898781;
    --gridline:       #e1e0d9;
    --baseline:       #c3c2b7;
    --border:         rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --surface-1:      #1a1a19;
      --page-plano:     #0d0d0d;
      --text-primary:   #ffffff;
      --text-secondary: #c3c2b7;
      --text-muted:     #898781;
      --gridline:       #2c2c2a;
      --baseline:       #383835;
      --border:         rgba(255,255,255,0.10);
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark;
    --surface-1:      #1a1a19;
    --page-plano:     #0d0d0d;
    --text-primary:   #ffffff;
    --text-secondary: #c3c2b7;
    --text-muted:     #898781;
    --gridline:       #2c2c2a;
    --baseline:       #383835;
    --border:         rgba(255,255,255,0.10);
  }}

  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--page-plano);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    color: var(--text-primary);
  }}
  .pagina {{ max-width: 920px; margin: 0 auto; padding: 32px 20px 64px; }}
  h1 {{ font-size: 1.4rem; margin: 0 0 4px; }}
  h2 {{ font-size: 1.05rem; margin: 0 0 4px; }}
  .subtitulo {{ color: var(--text-secondary); margin: 0 0 28px; font-size: 0.95rem; }}
  .subtitulo-cartao {{ color: var(--text-secondary); margin: 0 0 18px; font-size: 0.85rem; }}

  .cartao {{
    background: var(--surface-1);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px 22px;
    margin-bottom: 20px;
  }}

  .hero-label {{ color: var(--text-secondary); font-size: 0.85rem; margin: 0 0 6px; }}
  .hero-valor {{ font-size: 2.6rem; font-weight: 600; line-height: 1; }}
  .hero-valor small {{ font-size: 1rem; color: var(--text-muted); font-weight: 400; }}
  .hero-secundario {{ font-size: 0.8rem; color: var(--text-secondary); margin: 8px 0 0; }}
  .hero-secundario .valor-secundario {{ color: var(--text-muted); }}

  .grafico-barras-vertical {{
    display: flex;
    align-items: flex-end;
    gap: 14px;
    padding: 0 4px;
  }}
  .barra-vert-item {{
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: flex-end;
    flex: 1;
    height: 100%;
  }}
  .barra-vert-valor {{ font-size: 0.8rem; font-weight: 600; color: var(--text-primary); margin-bottom: 4px; font-variant-numeric: tabular-nums; }}
  .barra-vert-coluna {{ display: block; width: 60%; min-width: 18px; border-radius: 4px 4px 0 0; min-height: 2px; }}
  .barra-vert-rotulo {{ font-size: 0.75rem; color: var(--text-secondary); margin-top: 8px; text-align: center; }}

  .relatorio-cd {{ margin-bottom: 22px; padding-bottom: 18px; border-bottom: 1px solid var(--gridline); }}

  .grid-duas-colunas {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 28px;
  }}
  @media (max-width: 640px) {{
    .grid-duas-colunas {{ grid-template-columns: 1fr; }}
  }}
  .grafico-barras-horizontal {{ display: flex; flex-direction: column; gap: 6px; }}
  .barra-horiz-item {{ display: flex; align-items: center; gap: 8px; }}
  .barra-horiz-rotulo {{ width: 52px; flex-shrink: 0; font-size: 0.72rem; color: var(--text-secondary); }}
  .barra-horiz-trilha {{ flex: 1; background: var(--gridline); border-radius: 3px; height: 12px; overflow: hidden; }}
  .barra-horiz-barra {{ display: block; height: 100%; border-radius: 3px; min-width: 2px; }}
  .barra-horiz-valor {{ width: 34px; flex-shrink: 0; text-align: right; font-size: 0.75rem; font-weight: 600; color: var(--text-primary); font-variant-numeric: tabular-nums; }}

  details.tabela-acessivel summary {{
    cursor: pointer;
    color: var(--text-secondary);
    font-size: 0.9rem;
    padding: 4px 0;
  }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--gridline); }}
  th {{ color: var(--text-secondary); font-weight: 600; }}

  .nota {{ font-size: 0.78rem; color: var(--text-muted); margin-top: 10px; }}
</style>
</head>
<body>
<div class="viz-root">
  <div class="pagina">
    <h1>Meteorologia — Indicadores 4.1, 4.2 e 4.3</h1>
    <p class="subtitulo">Fonte: SIMGE (previsões do tempo e tendência climática), período 2026.</p>

    <div class="cartao">
      <h2>4.1 — Previsões do tempo publicadas</h2>
      <p class="subtitulo-cartao">Previsão esperada por dia útil (segunda a sexta, descontando feriados/facultativos)</p>
      {relatorio_cd_4_1_html}
      <p class="hero-label">Total de arquivos publicados no período</p>
      <div class="hero-valor">{total_4_1}</div>
      <div style="margin-top:18px;">
        {barras_dia_semana_html}
      </div>
    </div>
{cartao_4_2_html}
    <div class="cartao">
      <h2>4.3 — Monitoramento climático (tendência climática)</h2>
      {relatorio_cd_4_3_html}
      <p class="hero-label">Total de boletins no período</p>
      <div class="hero-valor">{total_4_3}</div>
      <div style="margin-top:18px;">
        {barras_mes_html}
      </div>
    </div>

    <details class="tabela-acessivel" open>
      <summary>Ver boletins de tendência climática (data e hora de criação)</summary>
      <table>
        <thead>
          <tr><th>Criado em</th><th>Boletim</th></tr>
        </thead>
        <tbody>{linhas_tabela_4_3}
        </tbody>
      </table>
    </details>
  </div>
</div>
</body>
</html>
"""

    with open(caminho_saida, "w", encoding="utf-8") as arquivo:
        arquivo.write(pagina)

    print(f"HTML de Meteorologia gerado em: {caminho_saida}")