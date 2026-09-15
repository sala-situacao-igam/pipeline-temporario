"""
Descrição: insere a barra de navegação entre as páginas do site
(index.html/Hidrometria e meteorologia.html/Meteorologia) num arquivo HTML
já gerado, sem alterar a geração em si -- é sempre um passo final, aplicado
depois que o arquivo já foi escrito no disco.

Conexões do Pipeline:
- Entradas: arquivo HTML já escrito em disco (index.html, de
  indicador_2_2_html.py, ou meteorologia.html, de indicador_meteorologia.py).
- Saídas: o mesmo arquivo, com a navegação injetada. Chamado por
  rodar_diario_hidro.py, rodar_diario_meteoro.py e gerar_relatorios_visuais.py.

Funções:
- injetar_nav: insere o HTML/CSS da barra de navegação num arquivo já existente.

Uso:
    from indicador_2_2_html import gerar_html_2_2
    from indicador_meteorologia import gerar_html_meteorologia
    from nav_site import injetar_nav

    gerar_html_2_2(df_pontuacao, "index.html")
    injetar_nav("index.html", "hidrometria")

    gerar_html_meteorologia(r_4_1, r_4_3, "meteorologia.html")
    injetar_nav("meteorologia.html", "meteorologia")
"""

NAV_HTML = """<nav class="nav-site">
  <a href="hidrometria.html" data-pagina="hidrometria">Hidrometria</a>
  <a href="meteorologia.html" data-pagina="meteorologia">Meteorologia</a>
</nav>
"""

NAV_CSS_TEMPLATE = """<style>
  .nav-site {{
    display: flex;
    gap: 4px;
    padding: 14px 20px 0;
    max-width: 920px;
    margin: 0 auto;
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size: 0.85rem;
  }}
  .nav-site a {{
    padding: 6px 12px;
    border-radius: 6px;
    text-decoration: none;
    color: #52514e;
  }}
  .nav-site a:hover {{ background: #e1e0d9; }}
  .nav-site a[data-pagina="{pagina_atual}"] {{
    background: #0b0b0b;
    color: #fff;
    font-weight: 600;
  }}
</style>
"""


def injetar_nav(caminho_html, pagina_atual):
    """Insere a barra de navegação num arquivo HTML já gerado.

    `pagina_atual`: "hidrometria" ou "meteorologia" -- só decide qual link
    fica destacado (comparação de atributo em CSS, não reescreve o HTML da
    barra em si).

    Idempotente: se chamado duas vezes no mesmo arquivo, insere duas vezes
    -- rode sempre a partir do HTML recém-gerado (não num arquivo que já
    passou por aqui antes), como no exemplo de uso no topo do arquivo.
    """
    with open(caminho_html, "r", encoding="utf-8") as f:
        conteudo = f.read()

    if "</head>" not in conteudo or "<body>" not in conteudo:
        raise ValueError(
            f"{caminho_html} não parece um HTML completo (falta <head>/<body>) -- "
            "confirme que é a saída de gerar_html_2_2()/gerar_html_meteorologia()."
        )

    css = NAV_CSS_TEMPLATE.format(pagina_atual=pagina_atual)
    conteudo = conteudo.replace("</head>", css + "</head>", 1)
    conteudo = conteudo.replace("<body>", "<body>\n" + NAV_HTML, 1)

    with open(caminho_html, "w", encoding="utf-8") as f:
        f.write(conteudo)

    print(f"Navegação inserida em: {caminho_html} (página atual: {pagina_atual})")
