"""
Descrição: insere a SEGUNDA barra de botões (sub-abas) logo abaixo da
navegação principal do site -- "Série histórica" / "Contrato de Gestão"
na Hidrologia e "2026" / "Contrato de Gestão" na Meteorologia.

Módulo NOVO e independente de nav_site.py (que não foi alterado): é um
passo final, aplicado DEPOIS de nav_site.injetar_nav(), no mesmo arquivo.

Conexões do Pipeline:
- Entradas: arquivo HTML já gerado e já com a nav principal
  (nav_site.injetar_nav).
- Saídas: o mesmo arquivo, com a sub-navegação. Chamado por
  dashboard_cg.py, meteorologia_cg.py e teste_colab_f1a.py (e, na Fase 1c,
  por rodar_diario_hidro.py/rodar_diario_meteoro.py também para as páginas
  de Série histórica/2026, para que os botões apareçam nas duas visões).

Uso:
    from nav_site import injetar_nav
    from nav_cg import injetar_subnav

    injetar_nav("hidrometria_cg.html", "hidrometria")
    injetar_subnav("hidrometria_cg.html", "hidrologia", "cg")
"""
import html as _html
import re

import config_cg

VISOES = {
    "hidrologia": [
        ("serie", "Série histórica", config_cg.PAGINA_HIDRO_SERIE),
        ("cg", "Contrato de Gestão", config_cg.PAGINA_HIDRO_CG),
        ("consistencia", "Consistência por Estação", config_cg.PAGINA_HIDRO_CONSISTENCIA),
    ],
    "meteorologia": [
        ("2026", "2026", config_cg.PAGINA_METEO_2026),
        ("cg", "Contrato de Gestão", config_cg.PAGINA_METEO_CG),
    ],
}

SUBNAV_CSS = """<style>
  .subnav-site {
    display: flex;
    gap: 0;
    padding: 10px 20px 0;
    max-width: 920px;
    margin: 0 auto;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 0.8rem;
  }
  .subnav-site a {
    padding: 5px 12px;
    text-decoration: none;
    color: #52514e;
    border: 1px solid #c3c2b7;
    background: transparent;
  }
  .subnav-site a:first-child { border-radius: 6px 0 0 6px; }
  .subnav-site a:last-child { border-radius: 0 6px 6px 0; border-left: none; }
  .subnav-site a:hover { background: #e1e0d9; }
  .subnav-site a[aria-current="page"] {
    background: #52514e;
    border-color: #52514e;
    color: #fff;
    font-weight: 600;
  }
  /* Modo escuro do navegador: a nav principal (nav_site.py) e esta
     sub-navegação ganham cores próprias -- sem isso o botão ativo da nav
     principal (fundo #0b0b0b) some no fundo escuro. Vem depois do CSS de
     nav_site.py, então sobrescreve com a mesma especificidade. */
  @media (prefers-color-scheme: dark) {
    .nav-site a { color: #c3c2b7; }
    .nav-site a:hover { background: #2c2c2a; }
    .nav-site a[data-pagina="__PAGINA__"] { background: #fff; color: #0b0b0b; }
    .subnav-site a { color: #c3c2b7; border-color: #4b4b47; }
    .subnav-site a:hover { background: #2c2c2a; }
    .subnav-site a[aria-current="page"] { background: #c3c2b7; border-color: #c3c2b7; color: #0b0b0b; }
  }
</style>
"""


def _subnav_html(secao, visao_atual):
    links = []
    for chave, rotulo, pagina in VISOES[secao]:
        atual = ' aria-current="page"' if chave == visao_atual else ""
        links.append(f'  <a href="{pagina}" data-visao="{chave}"{atual}>{_html.escape(rotulo)}</a>')
    return '<nav class="subnav-site" aria-label="Visão">\n' + "\n".join(links) + "\n</nav>\n"


def injetar_subnav(caminho_html, secao, visao_atual):
    """Insere a sub-navegação logo depois da nav principal (<nav class="nav-site">).

    `secao`: "hidrologia" ou "meteorologia".
    `visao_atual`: "serie" / "cg" (hidrologia) ou "2026" / "cg" (meteorologia).

    Como nav_site.injetar_nav, NÃO é idempotente -- rode sempre sobre o
    HTML recém-gerado."""
    if secao not in VISOES:
        raise ValueError(f"secao deve ser uma de {list(VISOES)}; recebido {secao!r}")
    if visao_atual not in {c for c, _, _ in VISOES[secao]}:
        raise ValueError(f"visao_atual inválida para {secao}: {visao_atual!r}")

    with open(caminho_html, "r", encoding="utf-8") as f:
        conteudo = f.read()

    match_nav = re.search(r'<nav class="nav-site">.*?</nav>\s*', conteudo, flags=re.S)
    if not match_nav or "</head>" not in conteudo:
        raise ValueError(
            f"{caminho_html}: nav principal não encontrada -- rode nav_site.injetar_nav() antes."
        )

    pagina_nav = "hidrometria" if secao == "hidrologia" else "meteorologia"
    css = SUBNAV_CSS.replace("__PAGINA__", pagina_nav)
    conteudo = conteudo.replace("</head>", css + "</head>", 1)
    match_nav = re.search(r'<nav class="nav-site">.*?</nav>\s*', conteudo, flags=re.S)
    fim_nav = match_nav.end()
    conteudo = conteudo[:fim_nav] + _subnav_html(secao, visao_atual) + conteudo[fim_nav:]

    with open(caminho_html, "w", encoding="utf-8") as f:
        f.write(conteudo)

    print(f"Sub-navegação inserida em: {caminho_html} ({secao} / {visao_atual})")
