"""
Descrição: calcula a disponibilidade dos dados hidrológicos e a pontuação
oficial do Anexo II (0-10) por estação para o indicador 2.2. 
A geração de HTML fica em indicador_2_2_html.py, que importa
este módulo. 
Quando a estação tem cota, a pontuação usa só cota (vazão
fica de fora por enquanto); quando é só-pluviométrica, usa chuva.

Agora também calcula a pontuação em paralelo para CHUVA (quando
disponível), permitindo visualizar duas perspectivas distintas:
- Gráfico de disponibilidade de COTA
- Gráfico de disponibilidade de CHUVA
Esses dois gráficos são independentes e não se misturam.

Conexões do Pipeline:
- Entradas: fato_disponibilidade.csv e dim_estacao.csv
  (config.PASTA_RELATORIOS_ID).
- Saídas: DataFrame de pontuação consumido por indicador_2_2_html.py,
  exportar_imagem_indicador_2_2.py e rodar_diario_hidro.py; opcionalmente
  salva relatorio_indicador_2_2.csv.

Funções:
- pontuar_percentual: converte um percentual de disponibilidade na pontuação 0-10 do Anexo II.
- calcular_pontuacao_2_2: calcula a pontuação por estação (COTA), usando tem_cota para decidir
  qual variável usar. Retorna apenas estações com tem_cota=True.
- calcular_pontuacao_2_2_chuva: calcula a pontuação usando APENAS chuva para TODAS as 68 estações,
  independente de tem_cota. Inclui pluviométricas puras E fluviométricas.
- distribuicao_pontuacao: conta quantas estações caem em cada faixa de pontuação.
- media_geral: calcula a pontuação média geral (0-10) entre as estações.
- media_percentual_geral: calcula o percentual médio geral de disponibilidade (0-100%).
- salvar_pontuacao_2_2: salva o DataFrame de pontuação como relatorio_indicador_2_2.csv no Drive.
"""

import pandas as pd

# Tabela de Calculo de Desempenho (CD) do Anexo II para 2.1/2.2
# Ordem do mais alto pro mais baixo importa
# para pontuar_percentual() abaixo.
TABELA_CD_2_2 = [
    (95.0, 10),
    (90.0, 9),
    (80.0, 8),
    (70.0, 7),
    (0.0, 0),
]

ORDEM_PONTUACAO = [10, 9, 8, 7, 0]

ROTULO_PONTUACAO = {
    10: "Ótima (10)",
    9: "Muito boa (9)",
    8: "Boa (8)",
    7: "Regular (7)",
    0: "Reprovada (0)",
}

# Cor de status fixa por pontuacao (nao muda entre tema claro/escuro)
STATUS_POR_PONTUACAO = {
    10: {"cor": "#0ca30c", "icone": "✓"},
    9:  {"cor": "#52c90de5", "icone": "✓"},
    8:  {"cor": "#fab219", "icone": "●"},
    7:  {"cor": "#ec835a", "icone": "▲"},
    0:  {"cor": "#d03b3b", "icone": "✕"},
}


def pontuar_percentual(percentual):
    """Converte um percentual bruto de disponibilidade na pontuacao 0-10 do
    Anexo II (tabela do 2.1/2.2). Usa a mesma tabela para qualquer percentual
    entre 0 e 100, seja ela calculada em cima de chuva ou de cota."""
    for limite, pontos in TABELA_CD_2_2:
        if percentual >= limite:
            return pontos
    return 0  # nao deveria cair aqui, mas fica como rede de seguranca


def calcular_pontuacao_2_2(fato_disponibilidade, dim_estacao):
    """Recebe o fato_disponibilidade (uma linha por estação x dia, com
    disponibilidade_chuva_percentual/disponibilidade_cota_percentual) e o
    dim_estacao (uma linha por estação, com tem_cota e ano_inicio_operacao)
    e devolve um DataFrame com uma linha por estação: variável usada, ano
    de início de operação, percentual médio no período todo, pontuação
    oficial (0-10) e ranking (1 = melhor estação).

    dim_estacao decide, por estação, se ela usa cota ou chuva (via
    tem_cota) e qual o ano_inicio_operacao -- atributos de estação, não do
    fato diário.
    
    COMPORTAMENTO ATUAL (legado):
    - Estações com tem_cota=True → usam cota
    - Estações com tem_cota=False → usam chuva
    - Gráfico reflete apenas essas variáveis selecionadas por estação."""
    colunas_fato_necessarias = [
        "codigo_estacao", "data_dia",
        "disponibilidade_chuva_percentual", "disponibilidade_cota_percentual",
    ]
    faltantes_fato = [c for c in colunas_fato_necessarias if c not in fato_disponibilidade.columns]
    if faltantes_fato:
        raise KeyError(
            "Colunas ausentes no fato_disponibilidade" 
            f"Faltando: {faltantes_fato}"
        )

    colunas_dim_necessarias = ["codigo_estacao", "tem_cota", "ano_inicio_operacao"]
    faltantes_dim = [c for c in colunas_dim_necessarias if c not in dim_estacao.columns]
    if faltantes_dim:
        raise KeyError(
            "Colunas ausentes no dim_estacao -- confira o dim_estacao.csv "
            f"da pasta 'relatorios' no Drive. Faltando: {faltantes_dim}"
        )

    df = fato_disponibilidade.copy()
    df["codigo_estacao"] = df["codigo_estacao"].astype(str).str.zfill(8)
    if not pd.api.types.is_datetime64_any_dtype(df["data_dia"]):
        df["data_dia"] = pd.to_datetime(df["data_dia"], format="mixed")

    dim = dim_estacao.copy()
    dim["codigo_estacao"] = dim["codigo_estacao"].astype(str).str.zfill(8)
    dim = dim.set_index("codigo_estacao")

    # Confere que toda estação do fato existe no dim_estacao ANTES de
    # calcular qualquer coisa -- se faltar, avisa com uma mensagem clara em
    # vez de deixar o merge gerar NaN silenciosamente (o que quebraria
    # pontuar_percentual() de um jeito confuso de diagnosticar depois).
    codigos_fato = set(df["codigo_estacao"].unique())
    codigos_dim = set(dim.index)
    faltando_no_dim = sorted(codigos_fato - codigos_dim)
    if faltando_no_dim:
        raise KeyError(
            "Estas estações aparecem no fato_disponibilidade mas ainda não "
            f"existem no dim_estacao.csv: {faltando_no_dim}. Adicione-as no "
            "dim_estacao.csv (pasta 'relatorios' do Drive) antes de rodar o "
            "cálculo do indicador 2.2 -- provavelmente uma frente nova que "
            "já foi ingerida mas ainda não foi cadastrada na dimensão."
        )

    linhas = []
    for codigo, grupo in df.groupby("codigo_estacao"):
        tem_cota = bool(dim.loc[codigo, "tem_cota"])
        variavel = "cota" if tem_cota else "chuva"
        coluna_percentual = (
            "disponibilidade_cota_percentual" if tem_cota else "disponibilidade_chuva_percentual"
        )

        percentual_medio = round(grupo[coluna_percentual].mean(), 2)
        pontuacao = pontuar_percentual(percentual_medio)

        ano_inicio = dim.loc[codigo, "ano_inicio_operacao"]

        linhas.append(
            {
                "codigo_estacao": codigo,
                "variavel_usada": variavel,
                "ano_inicio_operacao": int(ano_inicio) if pd.notna(ano_inicio) else None,
                "percentual_medio": percentual_medio,
                "pontuacao": pontuacao,
                "faixa": ROTULO_PONTUACAO[pontuacao],
            }
        )

    resumo = pd.DataFrame(linhas)
    resumo = resumo.sort_values(
        ["pontuacao", "percentual_medio"], ascending=[False, False]
    ).reset_index(drop=True)
    resumo.insert(0, "ranking", resumo.index + 1)

    return resumo


def calcular_pontuacao_2_2_chuva(fato_disponibilidade, dim_estacao):
    """Calcula a pontuação usando APENAS a variável CHUVA, para TODAS as
    estações (68), independente de tem_cota. Isso inclui:
    - Estações pluviométricas puras (tem_cota=False)
    - Estações fluviométricas que também coletam chuva (tem_cota=True)
    
    Retorna um DataFrame com mesma estrutura de calcular_pontuacao_2_2, 
    mas com variavel_usada='chuva' para todos.
    
    Usar este quando quiser ver um gráfico separado de disponibilidade de
    CHUVA, distinto do gráfico de COTA. O gráfico de chuva mostra as 68
    estações em sua totalidade.
    
    Devolve um DataFrame pronto para ordenação/ranking por pontuação."""
    colunas_fato_necessarias = [
        "codigo_estacao", "data_dia",
        "disponibilidade_chuva_percentual",
    ]
    faltantes_fato = [c for c in colunas_fato_necessarias if c not in fato_disponibilidade.columns]
    if faltantes_fato:
        raise KeyError(
            "Colunas ausentes no fato_disponibilidade para chuva. "
            f"Faltando: {faltantes_fato}"
        )

    colunas_dim_necessarias = ["codigo_estacao", "ano_inicio_operacao"]
    faltantes_dim = [c for c in colunas_dim_necessarias if c not in dim_estacao.columns]
    if faltantes_dim:
        raise KeyError(
            "Colunas ausentes no dim_estacao. "
            f"Faltando: {faltantes_dim}"
        )

    df = fato_disponibilidade.copy()
    df["codigo_estacao"] = df["codigo_estacao"].astype(str).str.zfill(8)
    if not pd.api.types.is_datetime64_any_dtype(df["data_dia"]):
        df["data_dia"] = pd.to_datetime(df["data_dia"], format="mixed")

    dim = dim_estacao.copy()
    dim["codigo_estacao"] = dim["codigo_estacao"].astype(str).str.zfill(8)
    dim = dim.set_index("codigo_estacao")

    # Validar que toda estação do fato existe no dim_estacao
    codigos_fato = set(df["codigo_estacao"].unique())
    codigos_dim = set(dim.index)
    faltando_no_dim = sorted(codigos_fato - codigos_dim)
    if faltando_no_dim:
        raise KeyError(
            "Estas estações aparecem no fato_disponibilidade mas ainda não "
            f"existem no dim_estacao.csv: {faltando_no_dim}."
        )

    linhas = []
    for codigo, grupo in df.groupby("codigo_estacao"):
        percentual_medio = round(grupo["disponibilidade_chuva_percentual"].mean(), 2)
        pontuacao = pontuar_percentual(percentual_medio)
        
        # Pega ano_inicio_operacao da dimensão (aplicável a todas as estações)
        ano_inicio = dim.loc[codigo, "ano_inicio_operacao"]

        linhas.append(
            {
                "codigo_estacao": codigo,
                "variavel_usada": "chuva",
                "ano_inicio_operacao": int(ano_inicio) if pd.notna(ano_inicio) else None,
                "percentual_medio": percentual_medio,
                "pontuacao": pontuacao,
                "faixa": ROTULO_PONTUACAO[pontuacao],
            }
        )

    resumo = pd.DataFrame(linhas)
    resumo = resumo.sort_values(
        ["pontuacao", "percentual_medio"], ascending=[False, False]
    ).reset_index(drop=True)
    resumo.insert(0, "ranking", resumo.index + 1)

    return resumo


def distribuicao_pontuacao(df_pontuacao):
    """Quantas estações caíram em cada faixa de pontuação (10, 9, 8, 7, 0),
    nessa ordem -- pronto para virar os 'tiles' de resumo no dashboard."""
    contagem = df_pontuacao["pontuacao"].value_counts().reindex(ORDEM_PONTUACAO, fill_value=0)
    return contagem.astype(int)


def media_geral(df_pontuacao):
    """Pontuação média geral (média das pontuações 0/7/8/9/10 por estação).

    Como a tabela do Anexo II pula de 0 direto pra 7 (não existe pontuação
    de 1 a 6), essa média pode cair numa faixa que nenhuma estação
    individual teria (ex.: 5,61) -- por isso o dashboard mostra este valor
    sempre junto com media_percentual_geral(), nunca isolado."""
    return round(df_pontuacao["pontuacao"].mean(), 2)


def media_percentual_geral(df_pontuacao):
    """Percentual médio geral (média do percentual_medio bruto de cada
    estação, 0-100%, antes de virar pontuação). Ao contrário de
    media_geral(), essa escala é contínua e não sofre do "buraco" entre 0 e
    7 da tabela de pontuação. Para converter de volta à pontuação oficial:
    pontuar_percentual(media_percentual_geral(df))."""
    return round(df_pontuacao["percentual_medio"].mean(), 2)


def salvar_pontuacao_2_2(servico, df_pontuacao, nome_arquivo="relatorio_indicador_2_2.csv"):
    """Salva a pontuação do indicador 2.2 como um relatório próprio no
    Drive (pasta de relatórios) -- substitui o arquivo inteiro a cada
    rodada.
    """
    import config
    import drive_io

    drive_io.salvar_csv(servico, df_pontuacao, nome_arquivo, config.PASTA_RELATORIOS_ID)
    print(f"Pontuação do indicador 2.2 salva em: {nome_arquivo}")
