"""
Descrição: ponto de entrada da execução diária de HIDROMETRIA via GitHub
Actions (pipeline_diario_hidro.yml) -- roda ingestão incremental (API
antiga, Frente 1), ingestão incremental (API nova -- Detalhada, indicador
2.1), pipeline de consistência e geração do dashboard (indicadores 2.1 +
2.2), em sequência.

Conexões do Pipeline:
- Entradas: chave de serviço (Secret do GitHub); ANA_IDENTIFICADOR/ANA_SENHA
  (Secrets do GitHub, credenciais da API nova); usa orquestrador.py,
  orquestrador_telemetria_detalhada.py, ingestao_ana_nova.py,
  pipeline_consistencia.py, drive_io.py, indicador_2_1_calculo.py,
  exportar_imagem_indicador_2_1.py, indicador_2_1_html.py,
  indicador_2_2_calculo.py, indicador_2_2_html.py, nav_site.py. Lê
  fato_disponibilidade.csv, dim_estacao.csv e os
  estacao_detalhada_XXXXXXXX.csv (config.PASTA_TELEMETRIA_DETALHADA_ID) do
  Drive.
- Saídas: index.html (CAMINHO_DASHBOARD_SAIDA, indicador 2.1 acima do 2.2),
  publicado no repositório público do dashboard (dashboard-igam) pelo
  workflow do GitHub Actions; fato_ultima_atualizacao_estacao.csv
  (config.PASTA_RELATORIOS_ID, acumulativo).

Funções:
- rodar_captura_telemetria_detalhada: roda a captura incremental da API
  nova (Frente 2.1) -- avisa e pula sem quebrar a rodada se as credenciais
  (Secrets) ainda não estiverem configuradas, ou se a captura falhar por
  outro motivo.
- gerar_dashboard: calcula a pontuação do indicador 2.2 e o CD do 2.1, gera
  o HTML (2.1 acima do 2.2) e injeta a navegação.
- main: executa Fase 2 (ingestão API antiga), Fase 3 (ingestão API nova),
  Fase 4 (consistência) e Fase 5 (dashboard) em sequência.

Se o fato_disponibilidade.csv ou o dim_estacao.csv ainda não existirem no
Drive, a geração do dashboard avisa e pula sem quebrar o resto da rodada.
O mesmo vale pro indicador 2.1 dentro do dashboard: se ainda não houver
nenhum estacao_detalhada_*.csv no Drive (captura nunca rodou com sucesso),
o cartão do 2.1 simplesmente não aparece nesta rodada -- o resto da página
(indicador 2.2) é gerado normalmente.

Uso local (Colab/terminal), se quiser rodar a sequência completa manualmente:
    CAMINHO_CHAVE_JSON=minha_chave.json ANA_IDENTIFICADOR=... ANA_SENHA=... python rodar_diario_hidro.py
Sem a variavel de ambiente definida, usa "chave_servico.json" como padrao
(nome que o workflow do GitHub Actions grava).

Pra testar SO a Fase 5 (sem rodar ingestao/consistencia de novo) no Colab,
antes de confiar nela dentro do workflow real:

    import config, drive_io, indicador_2_2_calculo, indicador_2_2_html, nav_site

    servico = drive_io.conectar_drive("sua_chave.json")
    fato = drive_io.ler_csv(servico, "fato_disponibilidade.csv", config.PASTA_RELATORIOS_ID)
    dim_estacao = drive_io.ler_csv(servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID)
    pontuacao = indicador_2_2_calculo.calcular_pontuacao_2_2(fato, dim_estacao)
    indicador_2_2_html.gerar_html_2_2(pontuacao, "index_teste.html")
    nav_site.injetar_nav("index_teste.html", "hidrometria")
    # abra index_teste.html no navegador (ou baixe do Colab) pra conferir
    # antes de deixar o workflow publicar de verdade.
"""
import os

import orquestrador
import pipeline_consistencia

CAMINHO_CHAVE = os.environ.get("CAMINHO_CHAVE_JSON", "chave_servico.json")
CAMINHO_DASHBOARD_SAIDA = os.environ.get("CAMINHO_DASHBOARD_SAIDA", "site_publicado/hidrometria.html")


def rodar_captura_telemetria_detalhada(caminho_chave):
    """Roda a captura incremental da API nova (rota Detalhada, indicador
    2.1) pra todas as estações da Frente 1. Não derruba a rodada inteira
    se der problema aqui: se ANA_IDENTIFICADOR/ANA_SENHA ainda não
    estiverem configurados como Secret, ou se a captura falhar por outro
    motivo (ex.: API fora do ar), só avisa e segue pra Fase 4/5 -- o
    indicador 2.2 não depende disso."""
    import ingestao_ana_nova
    import orquestrador_telemetria_detalhada

    try:
        identificador, senha = ingestao_ana_nova.ler_credenciais_ambiente()
    except EnvironmentError as erro:
        print(f"AVISO: {erro} -- pulando captura da API nova (indicador 2.1) nesta rodada.")
        return

    try:
        orquestrador_telemetria_detalhada.rodar_pipeline_detalhada(caminho_chave, identificador, senha)
    except Exception as erro:  # noqa: BLE001 -- falha aqui nao pode derrubar o 2.2
        print(f"AVISO: captura da API nova falhou ({type(erro).__name__}: {erro}) -- seguindo sem ela nesta rodada.")


def gerar_dashboard(caminho_chave, caminho_saida):
    """Lê o fato_disponibilidade.csv (já atualizado pela Fase 4) e o
    dim_estacao.csv, calcula a pontuação do indicador 2.2, gera o HTML do
    dashboard em caminho_saida (indicador 2.1 acima do 2.2) e injeta a
    barra de navegação (Hidrometria/Meteorologia). Não lança exceção se o
    fato_disponibilidade.csv ou o dim_estacao.csv ainda não existirem no
    Drive -- só avisa e retorna, para não derrubar a rodada inteira por
    causa do dashboard.

    O indicador 2.1 é calculado à parte, com sua própria proteção: se ainda
    não houver nenhum estacao_detalhada_*.csv no Drive, o cartão do 2.1 não
    entra na página desta vez, mas o 2.2 é gerado normalmente."""
    import config
    import drive_io
    import indicador_2_1_calculo
    import indicador_2_1_html
    import indicador_2_2_calculo
    import indicador_2_2_html
    import nav_site

    servico = drive_io.conectar_drive(caminho_chave)

    fato_disponibilidade = drive_io.ler_csv(
        servico, "fato_disponibilidade.csv", config.PASTA_RELATORIOS_ID
    )
    if fato_disponibilidade is None:
        print(
            "fato_disponibilidade.csv ainda nao existe no Drive -- "
            "pulando geracao do dashboard nesta rodada."
        )
        return

    dim_estacao = drive_io.ler_csv(
        servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID
    )
    if dim_estacao is None:
        print(
            "dim_estacao.csv ainda nao existe no Drive -- pulando geracao "
            "do dashboard nesta rodada."
        )
        return

    # -- indicador 2.1: cartao entra ACIMA do 2.2 nesta mesma pagina.
    # Reaproveita o fato_disponibilidade ja lido acima como universo das 64
    # estacoes (mesmo escopo do 2.2), em vez de ler o CSV de novo.
    cartao_2_1_html = ""
    estacoes_64 = sorted(
        fato_disponibilidade["codigo_estacao"].astype(str).str.zfill(8).unique().tolist()
    )
    try:
        df_pacotes = indicador_2_1_calculo.carregar_pacotes_telemetria_detalhada(
            servico, config.PASTA_TELEMETRIA_DETALHADA_ID
        )
    except RuntimeError as erro:
        print(f"AVISO: {erro} -- indicador 2.1 ainda sem dado, cartao nao entra nesta rodada.")
    else:
        # fato_ultima_atualizacao_estacao.csv -- acumulativo, atualizado a
        # cada rodada, independente do cartao do 2.1 ter dado certo ou nao.
        df_fato_ultima_atualizacao = indicador_2_1_calculo.gerar_fato_ultima_atualizacao(
            df_pacotes, estacoes_64
        )
        indicador_2_1_calculo.salvar_fato_ultima_atualizacao(servico, df_fato_ultima_atualizacao)

        estacoes_44 = sorted(df_pacotes["codigo_estacao"].unique().tolist())
        data_min = df_pacotes["Data_Hora_Medicao"].min()
        data_max = df_pacotes["Data_Hora_Medicao"].max()
        dias_periodo = (data_max.normalize() - data_min.normalize()).days + 1

        resultado_64 = indicador_2_1_calculo.calcular_cd_2_1(df_pacotes, estacoes_64, dias_periodo=dias_periodo)
        resultado_44 = indicador_2_1_calculo.calcular_cd_2_1(df_pacotes, estacoes_44, dias_periodo=dias_periodo)
        periodo_texto = f"Período considerado: {data_min:%d/%m/%Y} a {data_max:%d/%m/%Y}"

        cartao_2_1_html = indicador_2_1_html.gerar_cartao_2_1_html(resultado_64, resultado_44, periodo_texto)

    pasta_saida = os.path.dirname(caminho_saida)
    if pasta_saida:
        os.makedirs(pasta_saida, exist_ok=True)

    pontuacao = indicador_2_2_calculo.calcular_pontuacao_2_2(fato_disponibilidade, dim_estacao)
    indicador_2_2_html.gerar_html_2_2(pontuacao, caminho_saida, cartao_2_1_html=cartao_2_1_html)
    nav_site.injetar_nav(caminho_saida, "hidrometria")


def main():
    print("=== Fase 2: ingestao incremental API antiga (todas as estacoes da Frente 1) ===")
    orquestrador.rodar_pipeline(CAMINHO_CHAVE)

    print("\n=== Fase 3: ingestao incremental API nova -- Detalhada (indicador 2.1) ===")
    rodar_captura_telemetria_detalhada(CAMINHO_CHAVE)

    print("\n=== Fase 4: pipeline de consistencia (todas as estacoes) ===")
    pipeline_consistencia.rodar_para_todas_estacoes(CAMINHO_CHAVE)

    print("\n=== Fase 5: gerar dashboard (indicadores 2.1 + 2.2 + navegacao) ===")
    gerar_dashboard(CAMINHO_CHAVE, CAMINHO_DASHBOARD_SAIDA)

    print("\nExecucao diaria de hidrometria concluida.")


if __name__ == "__main__":
    main()
