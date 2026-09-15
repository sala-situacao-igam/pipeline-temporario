"""
Descrição: gera o dashboard HTML autocontido (CSS/JS embutidos) do
indicador 2.2, a partir da pontuação já calculada por
indicador_2_2_calculo.py. Só a parte de visualização mora aqui -- nenhum
cálculo de pontuação acontece neste arquivo.

NOVO: Suporta dois gráficos INDEPENDENTES:
- Gráfico de disponibilidade de COTA (68 estações, dados de cota)
- Gráfico de disponibilidade de CHUVA (68 estações, dados de chuva)

Cada gráfico tem seus próprios dados, filtros e cards (ótima, muito boa, etc).
O botão "Tipo de visualização" alterna entre eles.

Conexões do Pipeline:
- Entradas: DataFrames de pontuação de indicador_2_2_calculo.py (cota e chuva).
- Saídas: index.html, publicado no site (dashboard-igam) via
  rodar_diario_hidro.py/gerar_relatorios_visuais.py, depois passa por
  nav_site.injetar_nav().

Funções:
- gerar_html_2_2_dual: versão que aceita dados de cota E chuva e inclui seletor de gráfico.
"""

import html as _html
import json as _json

import pandas as pd

from indicador_2_2_calculo import (
    ORDEM_PONTUACAO,
    STATUS_POR_PONTUACAO,
    calcular_pontuacao_2_2,
    calcular_pontuacao_2_2_chuva,
    distribuicao_pontuacao,
    media_geral,
    media_percentual_geral,
)


def _tile_status_html(pontuacao, contagem, rotulo):
    """Monta um tile como <button> clicável, usado como filtro por faixa
    de pontuação. aria-pressed é alternado pelo JS conforme o filtro é ligado/desligado."""
    status = STATUS_POR_PONTUACAO[pontuacao]
    return f"""
        <button type="button" class="tile-status" data-pontuacao="{pontuacao}"
                aria-pressed="false" style="--cor-tile:{status['cor']};">
          <span class="icone-status" style="color:{status['cor']};">{status['icone']}</span>
          <span class="valor-tile">{contagem}</span>
          <span class="rotulo-tile">{_html.escape(rotulo)}</span>
        </button>"""


def _linha_tabela_html(row):
    percentual_fmt = f'{row["percentual_medio"]:.2f}'.replace(".", ",")
    return f"""
        <tr>
          <td>{row['ranking']}</td>
          <td>{_html.escape(str(row['codigo_estacao']))}</td>
          <td>{_html.escape(row['variavel_usada'])}</td>
          <td class="numero">{row['ano_inicio_operacao']}</td>
          <td class="numero">{percentual_fmt}%</td>
          <td class="numero">{row['pontuacao']}</td>
          <td>{_html.escape(row['faixa'])}</td>
        </tr>"""


def gerar_html_2_2_dual(fato_disponibilidade, dim_estacao, caminho_saida=None, cartao_2_1_html=""):
    """Gera HTML com DOIS gráficos INDEPENDENTES: cota e chuva.
    
    Cada gráfico:
    - Mostra 68 estações
    - Tem seus próprios dados de disponibilidade
    - Tem seus próprios cards (ótima, muito boa, boa, regular, reprovada)
    - Tem seus próprios filtros
    
    Não duplica dados. Cada gráfico é totalmente separado.
    
    Args:
        fato_disponibilidade: DataFrame com dados de disponibilidade
        dim_estacao: DataFrame com dimensão de estações
        caminho_saida: (opcional) path para salvar em arquivo
        cartao_2_1_html: (opcional) HTML do indicador 2.1 para incluir acima
    
    Returns:
        Se caminho_saida é None: retorna HTML como string
        Se caminho_saida é informado: salva em arquivo e imprime mensagem
    
    Exemplo de uso:
        # Retorna como string (para Colab)
        html_str = gerar_html_2_2_dual(fato, dim)
        display(HTML(html_str))
        
        # Salva em arquivo (para pipeline)
        gerar_html_2_2_dual(fato, dim, "output.html")
    """
    
    # ========================================================================
    # CÁLCULO DOS DADOS (dois DataFrames separados, sem duplicação)
    # ========================================================================
    
    # Dados para COTA (usa dim_estacao para saber quem tem cota)
    df_cota = calcular_pontuacao_2_2(fato_disponibilidade, dim_estacao)
    
    # Dados para CHUVA (calcula para TODAS as 68, independente de tem_cota)
    df_chuva = calcular_pontuacao_2_2_chuva(fato_disponibilidade, dim_estacao)
    
    # Ajustar a coluna variavel_usada do gráfico de chuva para refletir a realidade:
    # - Se tem_cota=True → "cota" (fluviométrica, coleta cota)
    # - Se tem_cota=False → "chuva" (pluviométrica, coleta chuva)
    # Isso permite o filtro "Variável usada" funcionar igual ao gráfico de cota
    dim_para_merge = dim_estacao.copy()
    dim_para_merge["codigo_estacao"] = dim_para_merge["codigo_estacao"].astype(str).str.zfill(8)
    dim_lookup = dim_para_merge.set_index("codigo_estacao")["tem_cota"]
    
    df_chuva["variavel_usada"] = df_chuva["codigo_estacao"].map(
        lambda cod: "cota" if dim_lookup.get(cod, False) else "chuva"
    )
    
    # ========================================================================
    # ESTATÍSTICAS POR GRÁFICO (independentes)
    # ========================================================================
    
    # Gráfico COTA
    distrib_cota = distribuicao_pontuacao(df_cota)
    media_cota = media_geral(df_cota)
    media_pct_cota = media_percentual_geral(df_cota)
    
    # Gráfico CHUVA
    distrib_chuva = distribuicao_pontuacao(df_chuva)
    media_chuva = media_geral(df_chuva)
    media_pct_chuva = media_percentual_geral(df_chuva)
    
    # ========================================================================
    # GERAÇÃO DO HTML (com dados separados em JSON)
    # ========================================================================
    
    # Tiles para COTA
    rotulos_tiles = {10: "Ótima (10)", 9: "Muito boa (9)", 8: "Boa (8)", 7: "Regular (7)", 0: "Reprovada (0)"}
    tiles_html_cota = "".join(_tile_status_html(p, distrib_cota[p], rotulos_tiles[p]) for p in ORDEM_PONTUACAO)
    
    # Tiles para CHUVA
    tiles_html_chuva = "".join(_tile_status_html(p, distrib_chuva[p], rotulos_tiles[p]) for p in ORDEM_PONTUACAO)
    
    # Tabelas para ambos (mesmo conteúdo, mas nomes de IDs diferentes)
    tabela_html_cota = "".join(_linha_tabela_html(row) for _, row in df_cota.iterrows())
    tabela_html_chuva = "".join(_linha_tabela_html(row) for _, row in df_chuva.iterrows())
    
    # JSON de dados para COTA
    colunas_dados = ["ranking", "codigo_estacao", "variavel_usada", "ano_inicio_operacao", "percentual_medio", "pontuacao", "faixa"]
    dados_json_cota = _json.dumps(
        df_cota[colunas_dados].to_dict(orient="records"), ensure_ascii=False
    ).replace("</", "<\\/")
    
    # JSON de dados para CHUVA
    dados_json_chuva = _json.dumps(
        df_chuva[colunas_dados].to_dict(orient="records"), ensure_ascii=False
    ).replace("</", "<\\/")
    
    # ========================================================================
    # CONSTRUÇÃO DO HTML
    # ========================================================================
    
    pagina = f"""<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hidrometria — Indicadores 2.1 e 2.2</title>
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
  .hero-valor--compacto {{ font-size: 2.2rem; }}
  .hero-valor--compacto small {{ font-size: 1rem; }}

  .grid-duas-colunas {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 28px;
  }}
  @media (max-width: 640px) {{
    .grid-duas-colunas {{ grid-template-columns: 1fr; }}
  }}

  .grade-tiles {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; }}
  .tile-status {{
    border: 1.5px solid;
    border-color: var(--border);
    border-radius: 8px;
    padding: 12px 8px;
    text-align: center;
    background: var(--surface-1);
    cursor: pointer;
    font: inherit;
    color: inherit;
    transition: background 0.1s ease, border-color 0.1s ease;
  }}
  .tile-status:hover {{ background: var(--gridline); }}
  .tile-status:focus-visible {{ outline: 2px solid var(--cor-tile); outline-offset: 1px; }}
  .tile-status[aria-pressed="true"] {{
    border-color: var(--cor-tile);
    background: color-mix(in srgb, var(--cor-tile) 12%, var(--surface-1));
  }}
  .icone-status {{ display: block; font-size: 1.1rem; margin-bottom: 2px; }}
  .valor-tile {{ display: block; font-size: 1.5rem; font-weight: 600; color: var(--text-primary); }}
  .rotulo-tile {{ display: block; font-size: 0.75rem; color: var(--text-secondary); margin-top: 2px; }}

  .barra-ferramentas {{
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px 16px;
    margin-bottom: 14px;
  }}
  .barra-ferramentas > * {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  label {{
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-secondary);
  }}
  select {{
    padding: 6px 10px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface-1);
    color: var(--text-primary);
    font: inherit;
    font-size: 0.9rem;
  }}

  .lista-estacoes {{
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin: 18px 0;
  }}
  .linha-estacao {{
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface-1);
    cursor: pointer;
    transition: background 0.15s ease, border-color 0.15s ease;
  }}
  .linha-estacao:hover {{
    background: var(--gridline);
    border-color: var(--baseline);
  }}
  .rotulo-estacao {{
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 0 0 140px;
    min-width: 0;
  }}
  .rotulo-principal {{
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .rotulo-secundario {{
    font-size: 0.75rem;
    color: var(--text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }}
  .trilha-barra {{
    display: flex;
    align-items: center;
    flex: 1;
    min-width: 0;
    height: 28px;
    background: var(--gridline);
    border-radius: 4px;
    padding: 0 6px;
  }}
  .barra {{
    display: block;
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s ease;
  }}
  .valor-barra {{
    flex: 0 0 auto;
    margin-left: 8px;
    font-size: 0.85rem;
    font-weight: 500;
    color: var(--text-primary);
    font-variant-numeric: tabular-nums;
  }}
  .valor-secundario {{
    color: var(--text-muted);
    margin-left: 4px;
  }}

  .contador-estacoes {{
    font-size: 0.85rem;
    color: var(--text-secondary);
    margin: 12px 0 0;
  }}

  .tabela-estacoes {{
    width: 100%;
    border-collapse: collapse;
    margin: 18px 0;
    font-size: 0.9rem;
  }}
  .tabela-estacoes thead {{
    border-bottom: 2px solid var(--baseline);
    background: var(--page-plano);
  }}
  .tabela-estacoes th {{
    padding: 10px 8px;
    text-align: left;
    font-weight: 600;
    color: var(--text-secondary);
  }}
  .tabela-estacoes th.th-ordenavel {{
    cursor: pointer;
    user-select: none;
    transition: background 0.1s ease;
  }}
  .tabela-estacoes th.th-ordenavel:hover {{
    background: var(--gridline);
  }}
  .tabela-estacoes td {{
    padding: 10px 8px;
    border-bottom: 1px solid var(--gridline);
  }}
  .tabela-estacoes tr:hover {{
    background: var(--gridline);
  }}
  .tabela-estacoes .numero {{
    font-variant-numeric: tabular-nums;
    text-align: right;
  }}
  .seta-ordenacao {{
    margin-left: 4px;
    color: var(--text-muted);
    font-size: 0.7rem;
  }}

  .botao-acao {{
    padding: 8px 14px;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface-1);
    color: var(--text-primary);
    font: inherit;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.1s ease, border-color 0.1s ease;
  }}
  .botao-acao:hover {{
    background: var(--gridline);
    border-color: var(--baseline);
  }}
  
  .grafico-container {{
    display: none;
  }}
  .grafico-container.ativo {{
    display: block;
  }}
</style>
</head>
<body class="viz-root">
<div class="pagina">
  {cartao_2_1_html}

  <div class="cartao">
    <h2>Disponibilidade de dados (Indicador 2.2)</h2>
    <p class="subtitulo-cartao">Variáveis monitoradas: cota, chuva e vazão</p>

    <!-- Seletor de tipo de gráfico -->
    <div style="margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--border);">
      <label style="display: block; margin-bottom: 8px; font-weight: 600;">Tipo de visualização:</label>
      <div style="display: flex; gap: 10px; flex-wrap: wrap;">
        <button type="button" class="botao-acao botao-tipo-viz" data-tipo="cota" aria-pressed="true">
          Disponibilidade de Cota
        </button>
        <button type="button" class="botao-acao botao-tipo-viz" data-tipo="chuva" aria-pressed="false">
          Disponibilidade de Chuva
        </button>
      </div>
      <p style="font-size: 0.8rem; color: var(--text-muted); margin: 10px 0 0; line-height: 1.4;">
        Cada gráfico mostra as 68 estações com seus próprios dados e cálculos de disponibilidade.
        O filtro "Variável usada" (abaixo) mostra quais estações coletam cada tipo de dado.
      </p>
    </div>

    <!-- ===== GRÁFICO COTA ===== -->
    <div id="grafico-cota" class="grafico-container ativo">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
        <div>
          <div class="hero-label">Pontuação média</div>
          <div class="hero-valor--compacto" id="media-pontuacao-cota">{media_cota:.2f}</div>
        </div>
        <div>
          <div class="hero-label">Disponibilidade média</div>
          <div class="hero-valor--compacto" id="media-percentual-cota">{media_pct_cota:.2f}<small>%</small></div>
        </div>
      </div>

      <h3 style="margin: 20px 0 12px; font-size: 0.95rem;">Distribuição por faixa</h3>
      <div class="grade-tiles" id="tiles-cota">
        {tiles_html_cota}
      </div>

      <h3 style="margin: 20px 0 12px; font-size: 0.95rem;">Filtros e visualização</h3>
      <div class="barra-ferramentas">
        <div>
          <label for="seletor-variavel-cota">Variável usada:</label>
          <select id="seletor-variavel-cota">
            <option value="todas">Todas</option>
            <option value="cota">Cota</option>
            <option value="chuva">Chuva</option>
          </select>
        </div>
        <div>
          <label for="seletor-ano-cota">Ano de início:</label>
          <select id="seletor-ano-cota">
            <option value="todas">Todas</option>
          </select>
        </div>
        <button type="button" class="botao-acao" id="botao-ordem-cota">Maior → menor ▾</button>
        <button type="button" class="botao-acao" id="botao-limpar-cota">Limpar filtros</button>
      </div>

      <div id="lista-estacoes-cota" class="lista-estacoes" role="list"></div>
      <div class="contador-estacoes" id="contador-cota"></div>

      <table class="tabela-estacoes">
        <thead>
          <tr>
            <th class="th-ordenavel" data-campo="ranking">Rank<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="codigo_estacao">Código<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="variavel_usada">Variável<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="ano_inicio_operacao">Ano<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="percentual_medio">Disponibilidade %<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="pontuacao">Pontuação<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="faixa">Faixa<span class="seta-ordenacao"></span></th>
          </tr>
        </thead>
        <tbody id="corpo-tabela-cota"></tbody>
      </table>
    </div>

    <!-- ===== GRÁFICO CHUVA ===== -->
    <div id="grafico-chuva" class="grafico-container">
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
        <div>
          <div class="hero-label">Pontuação média</div>
          <div class="hero-valor--compacto" id="media-pontuacao-chuva">{media_chuva:.2f}</div>
        </div>
        <div>
          <div class="hero-label">Disponibilidade média</div>
          <div class="hero-valor--compacto" id="media-percentual-chuva">{media_pct_chuva:.2f}<small>%</small></div>
        </div>
      </div>

      <h3 style="margin: 20px 0 12px; font-size: 0.95rem;">Distribuição por faixa</h3>
      <div class="grade-tiles" id="tiles-chuva">
        {tiles_html_chuva}
      </div>

      <h3 style="margin: 20px 0 12px; font-size: 0.95rem;">Filtros e visualização</h3>
      <div class="barra-ferramentas">
        <div>
          <label for="seletor-variavel-chuva">Variável usada:</label>
          <select id="seletor-variavel-chuva">
            <option value="todas">Todas</option>
            <option value="cota">Cota</option>
            <option value="chuva">Chuva</option>
          </select>
        </div>
        <div>
          <label for="seletor-ano-chuva">Ano de início:</label>
          <select id="seletor-ano-chuva">
            <option value="todas">Todas</option>
          </select>
        </div>
        <button type="button" class="botao-acao" id="botao-ordem-chuva">Maior → menor ▾</button>
        <button type="button" class="botao-acao" id="botao-limpar-chuva">Limpar filtros</button>
      </div>

      <div id="lista-estacoes-chuva" class="lista-estacoes" role="list"></div>
      <div class="contador-estacoes" id="contador-chuva"></div>

      <table class="tabela-estacoes">
        <thead>
          <tr>
            <th class="th-ordenavel" data-campo="ranking">Rank<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="codigo_estacao">Código<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="variavel_usada">Variável<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="ano_inicio_operacao">Ano<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="percentual_medio">Disponibilidade %<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="pontuacao">Pontuação<span class="seta-ordenacao"></span></th>
            <th class="th-ordenavel" data-campo="faixa">Faixa<span class="seta-ordenacao"></span></th>
          </tr>
        </thead>
        <tbody id="corpo-tabela-chuva"></tbody>
      </table>
    </div>
  </div>
</div>

<script>
(function() {{
  var CORES = {{
    0: "#d03b3b",
    7: "#ec835a",
    8: "#fab219",
    9: "#52c90de5",
    10: "#0ca30c",
  }};
  var LARGURA_MAX_PX = 280;
  
  // DADOS SEPARADOS (SEM DUPLICAÇÃO)
  var DADOS_COTA = {dados_json_cota};
  var DADOS_CHUVA = {dados_json_chuva};
  
  // Estado geral
  var estadoGeral = {{
    tipoVizAtual: "cota"
  }};
  
  // Estado do gráfico COTA
  var estadoCota = {{
    variavel: "todas",
    ano: "todas",
    ordem: "desc",
    faixasAtivas: {{}}
  }};
  
  // Estado do gráfico CHUVA
  var estadoChuva = {{
    variavel: "todas",
    ano: "todas",
    ordem: "desc",
    faixasAtivas: {{}}
  }};
  
  var estadoTabelaCota = {{
    campo: "ranking",
    direcao: "asc"
  }};
  
  var estadoTabelaChuva = {{
    campo: "ranking",
    direcao: "asc"
  }};

  function formatarPercentual(v) {{
    return v.toFixed(2).replace(".", ",") + "%";
  }}

  function algumFiltroDeFaixaAtivo(faixasAtivas) {{
    for (var chave in faixasAtivas) {{
      if (faixasAtivas[chave]) return true;
    }}
    return false;
  }}

  function aplicarFiltros(dados, estado) {{
    return dados.filter(function(d) {{
      if (estado.variavel !== "todas" && d.variavel_usada !== estado.variavel) return false;
      if (estado.ano !== "todas" && String(d.ano_inicio_operacao) !== estado.ano) return false;
      if (algumFiltroDeFaixaAtivo(estado.faixasAtivas) && !estado.faixasAtivas[d.pontuacao]) return false;
      return true;
    }});
  }}

  function popularFiltroAno(dados, seletorId) {{
    var anos = [];
    dados.forEach(function(d) {{
      if (anos.indexOf(d.ano_inicio_operacao) === -1) anos.push(d.ano_inicio_operacao);
    }});
    anos.sort(function(a, b) {{ return a - b; }});
    var seletor = document.getElementById(seletorId);
    anos.forEach(function(ano) {{
      var opcao = document.createElement("option");
      opcao.value = String(ano);
      opcao.textContent = String(ano);
      seletor.appendChild(opcao);
    }});
  }}

  function criarLinha(dado, posicao) {{
    var linha = document.createElement("div");
    linha.className = "linha-estacao";
    linha.tabIndex = 0;
    linha.setAttribute("role", "listitem");
    linha.setAttribute(
      "data-tooltip",
      "Estação " + dado.codigo_estacao + " — " + formatarPercentual(dado.percentual_medio) +
      " de disponibilidade de " + dado.variavel_usada + " — pontuação " + dado.pontuacao +
      " (" + dado.faixa + ") — em operação desde " + dado.ano_inicio_operacao
    );

    var rotulo = document.createElement("span");
    rotulo.className = "rotulo-estacao";
    var principal = document.createElement("span");
    principal.className = "rotulo-principal";
    principal.textContent = "#" + posicao + " · " + dado.codigo_estacao;
    var secundario = document.createElement("span");
    secundario.className = "rotulo-secundario";
    secundario.textContent = dado.variavel_usada + " · desde " + dado.ano_inicio_operacao;
    rotulo.appendChild(principal);
    rotulo.appendChild(secundario);

    var trilha = document.createElement("span");
    trilha.className = "trilha-barra";
    var barra = document.createElement("span");
    barra.className = "barra";
    barra.style.width = Math.max(3, Math.round((dado.percentual_medio / 100) * LARGURA_MAX_PX)) + "px";
    barra.style.background = CORES[dado.pontuacao];
    trilha.appendChild(barra);

    var valor = document.createElement("span");
    valor.className = "valor-barra";
    valor.textContent = formatarPercentual(dado.percentual_medio) + " ";
    var valorSecundario = document.createElement("span");
    valorSecundario.className = "valor-secundario";
    valorSecundario.textContent = "(" + dado.pontuacao + ")";
    valor.appendChild(valorSecundario);

    linha.appendChild(rotulo);
    linha.appendChild(trilha);
    linha.appendChild(valor);
    return linha;
  }}

  function renderizar(tipo) {{
    var dados = tipo === "cota" ? DADOS_COTA : DADOS_CHUVA;
    var estado = tipo === "cota" ? estadoCota : estadoChuva;
    var listaEl = document.getElementById("lista-estacoes-" + tipo);
    var contadorEl = document.getElementById("contador-" + tipo);
    var mediaElement = document.getElementById("media-pontuacao-" + tipo);
    var mediaPercentualElement = document.getElementById("media-percentual-" + tipo);

    var filtrados = aplicarFiltros(dados, estado);

    filtrados.sort(function(a, b) {{
      var diferenca = a.percentual_medio - b.percentual_medio;
      return estado.ordem === "desc" ? -diferenca : diferenca;
    }});

    listaEl.textContent = "";
    filtrados.forEach(function(dado, indice) {{
      listaEl.appendChild(criarLinha(dado, indice + 1));
    }});

    contadorEl.textContent = "Mostrando " + filtrados.length + " de " + dados.length + " estações";

    // Atualizar médias
    if (filtrados.length > 0) {{
      var somapontos = 0;
      var somaPercent = 0;
      filtrados.forEach(function(d) {{
        somapontos += d.pontuacao;
        somaPercent += d.percentual_medio;
      }});
      var mediaPts = (somapontos / filtrados.length).toFixed(2);
      var mediaPct = (somaPercent / filtrados.length).toFixed(2);
      mediaElement.textContent = mediaPts;
      mediaPercentualElement.textContent = mediaPct.replace(".", ",");
    }}
  }}

  function compararValores(a, b, campo) {{
    var va = a[campo];
    var vb = b[campo];
    if (typeof va === "number" && typeof vb === "number") return va - vb;
    return String(va).localeCompare(String(vb), "pt-BR");
  }}

  function criarLinhaTabela(dado) {{
    var tr = document.createElement("tr");
    var celulas = [
      {{ texto: String(dado.ranking), numero: false }},
      {{ texto: dado.codigo_estacao, numero: false }},
      {{ texto: dado.variavel_usada, numero: false }},
      {{ texto: String(dado.ano_inicio_operacao), numero: true }},
      {{ texto: formatarPercentual(dado.percentual_medio), numero: true }},
      {{ texto: String(dado.pontuacao), numero: true }},
      {{ texto: dado.faixa, numero: false }}
    ];
    celulas.forEach(function(c) {{
      var td = document.createElement("td");
      if (c.numero) td.className = "numero";
      td.textContent = c.texto;
      tr.appendChild(td);
    }});
    return tr;
  }}

  function atualizarSetasOrdenacao(tipo) {{
    var cabecalhosOrdenaveis = document.querySelectorAll("#grafico-" + tipo + " th.th-ordenavel");
    var estadoTabela = tipo === "cota" ? estadoTabelaCota : estadoTabelaChuva;
    
    cabecalhosOrdenaveis.forEach(function(th) {{
      var seta = th.querySelector(".seta-ordenacao");
      var campo = th.getAttribute("data-campo");
      seta.textContent = campo === estadoTabela.campo
        ? (estadoTabela.direcao === "asc" ? "▲" : "▼")
        : "";
    }});
  }}

  function renderTabela(tipo) {{
    var dados = tipo === "cota" ? DADOS_COTA : DADOS_CHUVA;
    var estado = tipo === "cota" ? estadoCota : estadoChuva;
    var estadoTabela = tipo === "cota" ? estadoTabelaCota : estadoTabelaChuva;
    var corpoTabela = document.getElementById("corpo-tabela-" + tipo);

    var filtrados = aplicarFiltros(dados, estado);
    filtrados.sort(function(a, b) {{
      var resultado = compararValores(a, b, estadoTabela.campo);
      return estadoTabela.direcao === "asc" ? resultado : -resultado;
    }});

    corpoTabela.textContent = "";
    filtrados.forEach(function(dado) {{
      corpoTabela.appendChild(criarLinhaTabela(dado));
    }});
    atualizarSetasOrdenacao(tipo);
  }}

  // Botões de tipo de visualização
  document.querySelectorAll(".botao-tipo-viz").forEach(function(btn) {{
    btn.addEventListener("click", function() {{
      var tipo = btn.getAttribute("data-tipo");
      estadoGeral.tipoVizAtual = tipo;

      document.getElementById("grafico-cota").classList.toggle("ativo", tipo === "cota");
      document.getElementById("grafico-chuva").classList.toggle("ativo", tipo === "chuva");

      document.querySelectorAll(".botao-tipo-viz").forEach(function(b) {{
        b.setAttribute("aria-pressed", b.getAttribute("data-tipo") === tipo ? "true" : "false");
      }});
    }});
  }});

  // Eventos do gráfico COTA
  document.getElementById("seletor-variavel-cota").addEventListener("change", function() {{
    estadoCota.variavel = this.value;
    renderizar("cota");
    renderTabela("cota");
  }});

  document.getElementById("seletor-ano-cota").addEventListener("change", function() {{
    estadoCota.ano = this.value;
    renderizar("cota");
    renderTabela("cota");
  }});

  document.getElementById("botao-ordem-cota").addEventListener("click", function() {{
    estadoCota.ordem = estadoCota.ordem === "desc" ? "asc" : "desc";
    this.textContent = estadoCota.ordem === "desc" ? "Maior → menor ▾" : "Menor → maior ▴";
    renderizar("cota");
  }});

  document.getElementById("botao-limpar-cota").addEventListener("click", function() {{
    estadoCota.variavel = "todas";
    estadoCota.ano = "todas";
    estadoCota.ordem = "desc";
    estadoCota.faixasAtivas = {{}};
    document.getElementById("seletor-variavel-cota").value = "todas";
    document.getElementById("seletor-ano-cota").value = "todas";
    document.getElementById("botao-ordem-cota").textContent = "Maior → menor ▾";
    document.querySelectorAll("#grafico-cota .tile-status").forEach(function(t) {{
      t.setAttribute("aria-pressed", "false");
    }});
    renderizar("cota");
    renderTabela("cota");
  }});

  document.querySelectorAll("#grafico-cota .tile-status").forEach(function(tile) {{
    tile.addEventListener("click", function() {{
      var pontos = tile.getAttribute("data-pontuacao");
      var ativo = tile.getAttribute("aria-pressed") === "true";
      estadoCota.faixasAtivas[pontos] = !ativo;
      tile.setAttribute("aria-pressed", String(!ativo));
      renderizar("cota");
      renderTabela("cota");
    }});
  }});

  document.querySelectorAll("#grafico-cota th.th-ordenavel").forEach(function(th) {{
    th.addEventListener("click", function() {{
      var campo = th.getAttribute("data-campo");
      if (estadoTabelaCota.campo === campo) {{
        estadoTabelaCota.direcao = estadoTabelaCota.direcao === "asc" ? "desc" : "asc";
      }} else {{
        estadoTabelaCota.campo = campo;
        estadoTabelaCota.direcao = "asc";
      }}
      renderTabela("cota");
    }});
  }});

  // Eventos do gráfico CHUVA
  document.getElementById("seletor-variavel-chuva").addEventListener("change", function() {{
    estadoChuva.variavel = this.value;
    renderizar("chuva");
    renderTabela("chuva");
  }});

  document.getElementById("seletor-ano-chuva").addEventListener("change", function() {{
    estadoChuva.ano = this.value;
    renderizar("chuva");
    renderTabela("chuva");
  }});

  document.getElementById("botao-ordem-chuva").addEventListener("click", function() {{
    estadoChuva.ordem = estadoChuva.ordem === "desc" ? "asc" : "desc";
    this.textContent = estadoChuva.ordem === "desc" ? "Maior → menor ▾" : "Menor → maior ▴";
    renderizar("chuva");
  }});

  document.getElementById("botao-limpar-chuva").addEventListener("click", function() {{
    estadoChuva.variavel = "todas";
    estadoChuva.ano = "todas";
    estadoChuva.ordem = "desc";
    estadoChuva.faixasAtivas = {{}};
    document.getElementById("seletor-variavel-chuva").value = "todas";
    document.getElementById("seletor-ano-chuva").value = "todas";
    document.getElementById("botao-ordem-chuva").textContent = "Maior → menor ▾";
    document.querySelectorAll("#grafico-chuva .tile-status").forEach(function(t) {{
      t.setAttribute("aria-pressed", "false");
    }});
    renderizar("chuva");
    renderTabela("chuva");
  }});

  document.querySelectorAll("#grafico-chuva .tile-status").forEach(function(tile) {{
    tile.addEventListener("click", function() {{
      var pontos = tile.getAttribute("data-pontuacao");
      var ativo = tile.getAttribute("aria-pressed") === "true";
      estadoChuva.faixasAtivas[pontos] = !ativo;
      tile.setAttribute("aria-pressed", String(!ativo));
      renderizar("chuva");
      renderTabela("chuva");
    }});
  }});

  document.querySelectorAll("#grafico-chuva th.th-ordenavel").forEach(function(th) {{
    th.addEventListener("click", function() {{
      var campo = th.getAttribute("data-campo");
      if (estadoTabelaChuva.campo === campo) {{
        estadoTabelaChuva.direcao = estadoTabelaChuva.direcao === "asc" ? "desc" : "asc";
      }} else {{
        estadoTabelaChuva.campo = campo;
        estadoTabelaChuva.direcao = "asc";
      }}
      renderTabela("chuva");
    }});
  }});

  // Inicialização
  popularFiltroAno(DADOS_COTA, "seletor-ano-cota");
  popularFiltroAno(DADOS_CHUVA, "seletor-ano-chuva");
  renderizar("cota");
  renderTabela("cota");
  renderizar("chuva");
  renderTabela("chuva");
}})();
</script>
</body>
</html>
"""

    # ========================================================================
    # SALVAR OU RETORNAR
    # ========================================================================
    
    if caminho_saida is None:
        return pagina
    else:
        with open(caminho_saida, "w", encoding="utf-8") as arquivo:
            arquivo.write(pagina)
        print(f"HTML de Hidrometria gerado em: {caminho_saida}")


def gerar_html_2_2(df_pontuacao, caminho_saida, cartao_2_1_html=""):
    """Função compatível com o pipeline existente.
    
    Recebe um DataFrame de pontuação (como antes) e o converte internamente
    em dois gráficos (cota e chuva) para usar a função gerar_html_2_2_dual.
    
    Para usar:
        gerar_html_2_2(df_pontuacao, "index.html", cartao_2_1_html=cartao_html)
    
    Internamente, ela:
    1. Carrega os dados novamente (necessário para ter os dois gráficos separados)
    2. Chama gerar_html_2_2_dual com os dados brutos
    3. Salva em arquivo
    
    Args:
        df_pontuacao: DataFrame de pontuação (pode ser ignorado, mantido por compatibilidade)
        caminho_saida: path onde salvar o HTML
        cartao_2_1_html: HTML do indicador 2.1 para incluir acima
    """
    # Aviso: esta função espera que fato_disponibilidade e dim_estacao
    # estejam disponíveis no escopo global (como estão em gerar_relatorios_visuais.py)
    # Se não estiverem, você precisa chamar gerar_html_2_2_dual() diretamente
    
    import drive_io
    import config
    
    try:
        # Tentar carregar os dados do Drive (se estiver rodando via pipeline)
        servico = drive_io.conectar_drive("chave_servico.json")
        fato_disponibilidade = drive_io.ler_csv(servico, "fato_disponibilidade.csv", config.PASTA_RELATORIOS_ID)
        dim_estacao = drive_io.ler_csv(servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID)
    except:
        # Se não conseguir carregar do Drive, assumir que foram passados globalmente
        # (como em gerar_relatorios_visuais.py)
        import sys
        frame = sys._getframe(1)
        fato_disponibilidade = frame.f_locals.get("fato_disponibilidade")
        dim_estacao = frame.f_locals.get("dim_estacao")
    
    # Chamar a função dual que gera o HTML com dois gráficos
    gerar_html_2_2_dual(
        fato_disponibilidade,
        dim_estacao,
        caminho_saida=caminho_saida,
        cartao_2_1_html=cartao_2_1_html
    )
