"""
Descrição: ponto de entrada da execução diária de HIDROMETRIA via GitHub
Actions (pipeline_diario_hidro.yml) -- ingestão incremental (API antiga,
Frente 1), ingestão incremental (API nova -- Detalhada, indicador 2.1),
pipeline de consistência (disponibilidade 2.2 + indicador 2.8) e geração
das DUAS páginas de Hidrologia, em sequência.

ATUALIZADO (29/09/2026 -- gráficos do relatório mensal):
- Depois da página do Contrato de Gestão, a Fase 5 gera os PNGs do
  relatório (2.1, 2.2, 2.8 -- gerar_relatorios_visuais.py) com os mesmos
  números da página e SOBRESCREVE os arquivos na pasta do Drive
  config_cg.PASTA_GRAFICOS_RELATORIO_ID. Falha nos gráficos só gera aviso.

ATUALIZADO (29/09/2026 -- aba "Consistência por Estação"):
- Fase 5 agora gera TRÊS páginas (paginas_hidrologia.py +
  pagina_consistencia_estacao.py):
    hidrometria.html               -> visão "Série histórica"
    hidrometria_cg.html            -> visão "Contrato de Gestão" (2.1, 2.2 e 2.8)
    hidrometria_consistencia.html  -> visão "Consistência por Estação" (painel
                                       interativo de chuva/nível por estação,
                                       com uma pasta dados_consistencia/ ao lado)
  As três vão para a pasta do repositório público (PASTA_SITE, incluindo a
  subpasta de dados), e o workflow publica as três. Se a página de
  Consistência ou a de Contrato de Gestão falhar, as demais são publicadas
  mesmo assim (a falha fica no log).

ATUALIZADO (27/09/2026 -- Contrato de Gestão + novo layout):
- Fase 4 usa o pipeline_consistencia NOVO (testes do 2.8; Step desligado).
- Fase 5 gera, no novo layout (paginas_hidrologia.py):
    hidrometria.html     -> visão "Série histórica"
    hidrometria_cg.html  -> visão "Contrato de Gestão" (2.1, 2.2 e 2.8)
  As duas vão para a pasta do repositório público (PASTA_SITE), e o
  workflow publica as duas. Se só a página do Contrato de Gestão falhar,
  a Série histórica é publicada mesmo assim (a falha fica no log).

Conexões do Pipeline:
- Entradas: chave de serviço (Secret); ANA_IDENTIFICADOR/ANA_SENHA (Secrets,
  API nova); EE_PROJECT (opcional, projeto do Earth Engine para o CHIRPS).
  Usa orquestrador.py, orquestrador_telemetria_detalhada.py,
  ingestao_ana_nova.py, pipeline_consistencia.py, indicador_2_1_calculo.py,
  paginas_hidrologia.py, config_cg.py, drive_io.py.
- Saídas: hidrometria.html e hidrometria_cg.html (PASTA_SITE);
  fato_att_api_nova.csv (config.PASTA_RELATORIOS_ID) e os relatórios do
  pipeline_consistencia.

Uso local (Colab/terminal):
    CAMINHO_CHAVE_JSON=minha_chave.json ANA_IDENTIFICADOR=... ANA_SENHA=... python rodar_diario_hidro.py
"""
import os

import orquestrador
import pipeline_consistencia

CAMINHO_CHAVE = os.environ.get("CAMINHO_CHAVE_JSON", "chave_servico.json")
PASTA_SITE = os.environ.get("PASTA_SITE", "site_publicado")


def rodar_captura_telemetria_detalhada(caminho_chave):
    """Igual à versão anterior: captura da API nova (2.1); avisa e segue se falhar."""
    import ingestao_ana_nova
    import orquestrador_telemetria_detalhada

    try:
        identificador, senha = ingestao_ana_nova.ler_credenciais_ambiente()
    except EnvironmentError as erro:
        print(f"AVISO: {erro} -- pulando captura da API nova (indicador 2.1) nesta rodada.")
        return
    try:
        orquestrador_telemetria_detalhada.rodar_pipeline_detalhada(caminho_chave, identificador, senha)
    except Exception as erro:  # noqa: BLE001
        print(f"AVISO: captura da API nova falhou ({type(erro).__name__}: {erro}) -- seguindo sem ela nesta rodada.")


def gerar_paginas(caminho_chave, pasta_site, resultados_consistencia=None):
    """Gera hidrometria.html (Série histórica), hidrometria_cg.html
    (Contrato de Gestão) e hidrometria_consistencia.html (Consistência
    por Estação, 29/09/2026 -- painel interativo por estação, adaptado da
    interface feita por um colega da equipe; ver decisoes_e_progresso.md)
    em pasta_site."""
    import config
    import config_cg
    import drive_io
    import fato_consistencia_estacao
    import indicador_2_1_calculo
    import indicador_2_8_calculo
    import pagina_consistencia_estacao
    import paginas_hidrologia

    servico = drive_io.conectar_drive(caminho_chave)
    config_cg.carregar_exclusoes_do_drive(servico)

    fato = drive_io.ler_csv(servico, "fato_disponibilidade.csv", config.PASTA_RELATORIOS_ID)
    dim = drive_io.ler_csv(servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID)
    if fato is None or dim is None:
        print("fato_disponibilidade.csv ou dim_estacao.csv ainda não existe no Drive -- páginas não geradas.")
        return

    # 2.1 -- pacotes da API nova + fato_att_api_nova.csv (igual a antes)
    try:
        pacotes = indicador_2_1_calculo.carregar_pacotes_telemetria_detalhada(
            servico, config.PASTA_TELEMETRIA_DETALHADA_ID)
        universo = sorted(fato["codigo_estacao"].astype(str).str.zfill(8).unique().tolist())
        indicador_2_1_calculo.salvar_fato_ultima_atualizacao(
            servico, indicador_2_1_calculo.gerar_fato_ultima_atualizacao(pacotes, universo))
    except RuntimeError as erro:
        print(f"AVISO: {erro} -- 2.1 sem dado nesta rodada.")
        pacotes = None

    # 2.8 -- do que a Fase 4 acabou de calcular; senão, do Drive
    resultados_consistencia = resultados_consistencia or {}
    resumo = resultados_consistencia.get("resumo_2_8")
    por_estacao = resultados_consistencia.get("por_estacao_2_8")
    if resumo is None:
        resumo = drive_io.ler_csv(servico, indicador_2_8_calculo.NOME_RESUMO, config.PASTA_RELATORIOS_ID)
    if por_estacao is None:
        por_estacao = drive_io.ler_csv(servico, indicador_2_8_calculo.NOME_POR_ESTACAO, config.PASTA_RELATORIOS_ID)

    fato_estacao = resultados_consistencia.get("fato_consistencia_estacao")
    if fato_estacao is None:
        fato_estacao = drive_io.ler_csv(servico, fato_consistencia_estacao.NOME_ARQUIVO_FATO, config.PASTA_RELATORIOS_ID)

    os.makedirs(pasta_site, exist_ok=True)
    print(paginas_hidrologia.gerar_hidro_serie(fato, dim, pacotes, os.path.join(pasta_site, config_cg.PAGINA_HIDRO_SERIE)))
    dados_cg = None
    try:
        resumo_cg, dados_cg = paginas_hidrologia.gerar_hidro_cg(
            fato, dim, pacotes, resumo, os.path.join(pasta_site, config_cg.PAGINA_HIDRO_CG),
            por_estacao_2_8=por_estacao, devolver_dados=True)
        print(resumo_cg)
    except Exception as erro:  # noqa: BLE001 -- a Série histórica já foi gerada e segue publicada
        print(f"ERRO na página do Contrato de Gestão ({type(erro).__name__}: {erro}) -- "
              "a Série histórica será publicada mesmo assim.")

    # Gráficos do relatório mensal (29/09/2026): desenhados a partir do MESMO
    # `dados` da página do Contrato de Gestão e sobrescritos no Drive a cada
    # rodada. Uma falha aqui só gera aviso -- nunca impede a publicação.
    if dados_cg is not None:
        try:
            import gerar_relatorios_visuais
            gerar_relatorios_visuais.gerar_e_publicar_hidro(dados_cg, servico)
        except Exception as erro:  # noqa: BLE001
            print(f"AVISO: gráficos do relatório (hidro) não atualizados ({type(erro).__name__}: {erro}).")
    try:
        pagina_consistencia_estacao.gerar_pagina_consistencia(
            fato_estacao, dim, os.path.join(pasta_site, config_cg.PAGINA_HIDRO_CONSISTENCIA))
    except Exception as erro:  # noqa: BLE001 -- as outras duas páginas já foram geradas e seguem publicadas
        print(f"ERRO na página de Consistência por Estação ({type(erro).__name__}: {erro}) -- "
              "as demais páginas serão publicadas mesmo assim.")


def main():
    print("=== Fase 2: ingestao incremental API antiga (todas as estacoes da Frente 1) ===")
    orquestrador.rodar_pipeline(CAMINHO_CHAVE)

    print("\n=== Fase 3: ingestao incremental API nova -- Detalhada (indicador 2.1) ===")
    rodar_captura_telemetria_detalhada(CAMINHO_CHAVE)

    print("\n=== Fase 4: consistencia (disponibilidade 2.2 + indicador 2.8) ===")
    resultados = pipeline_consistencia.rodar_para_todas_estacoes(CAMINHO_CHAVE)

    print("\n=== Fase 5: paginas de Hidrologia (Serie historica + Contrato de Gestao) ===")
    gerar_paginas(CAMINHO_CHAVE, PASTA_SITE, resultados)

    print("\nExecucao diaria de hidrometria concluida.")


if __name__ == "__main__":
    main()
