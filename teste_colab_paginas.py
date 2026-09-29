"""
Descrição: TESTE no Colab da etapa 2 da Fase 1b -- gera as QUATRO páginas
no novo layout com dados reais, numa pasta local "saida_paginas/", SEM
gravar nada no Drive e SEM publicar no GitHub.

Só LÊ do Drive: fato_disponibilidade.csv, dim_estacao.csv, os
estacao_detalhada_*.csv (2.1) e -- se ainda não houver o arquivo local --
o indicador_2_8_resumo.csv. O resumo do 2.8 é procurado primeiro em
saida_teste_2_8/indicador_2_8_resumo.csv (gerado pelo
teste_colab_f1b_2_8.py), porque o pipeline oficial ainda não gravou esse
arquivo no Drive.

Como usar no Colab:
1. Upload na raiz: chave_servico.json, os .py do repositório e, POR ÚLTIMO,
   os .py de scripts_dash_cg.
2. Rode antes o teste_colab_f1b_2_8.py (para ter o resumo do 2.8), ou
   deixe sem -- a página do Contrato de Gestão sai sem a seção do 2.8 e
   com um aviso.
3. %run teste_colab_paginas.py   -> baixa saida_paginas.zip
4. Abra os 4 HTML no navegador (os botões navegam entre eles). Teste
   também com o navegador/sistema em modo escuro.
"""
import os
import shutil

import pandas as pd

import config
import config_cg
import drive_io
import indicador_2_1_calculo
import indicador_2_8_calculo
import meteorologia_cg
import paginas_hidrologia

CAMINHO_CHAVE = os.environ.get("CAMINHO_CHAVE_JSON", "chave_servico.json")
PASTA_SAIDA = "saida_paginas"
RESUMO_LOCAL = os.path.join("saida_teste_2_8", "indicador_2_8_resumo.csv")
RODAR_METEOROLOGIA = True  # False para testar só a Hidrologia (a raspagem do SIMGE demora)


def testar_busca_automatica_pasta():
    """Confere a busca automática da pasta do ano no SIMGE (usada a partir de
    2027) procurando 2025 e 2026 SEM usar o config_cg, e compara com os
    folderIds conhecidos."""
    import re
    conhecidos = {("previsoes", 2026): "9814139", ("previsoes", 2025): "9138421",
                  ("tendencia", 2026): "9867148", ("tendencia", 2025): "8989057"}
    original = config_cg.URLS_SIMGE_POR_ANO
    config_cg.URLS_SIMGE_POR_ANO = {}
    try:
        print("\n=== Teste da busca automática da pasta do ano (SIMGE) ===")
        for (tipo, ano), esperado in conhecidos.items():
            url = meteorologia_cg.descobrir_url_pasta_ano(tipo, ano)
            achado = re.search(r"view/(\d+)", url).group(1) if url else None
            status = "OK" if achado == esperado else "FALHOU"
            print(f"  {tipo} {ano}: achado={achado} esperado={esperado} -> {status}")
    finally:
        config_cg.URLS_SIMGE_POR_ANO = original


def main():
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    caminho = lambda nome: os.path.join(PASTA_SAIDA, nome)
    servico = drive_io.conectar_drive(CAMINHO_CHAVE)

    fato = drive_io.ler_csv(servico, "fato_disponibilidade.csv", config.PASTA_RELATORIOS_ID)
    dim = drive_io.ler_csv(servico, "dim_estacao.csv", config.PASTA_RELATORIOS_ID)
    try:
        pacotes = indicador_2_1_calculo.carregar_pacotes_telemetria_detalhada(
            servico, config.PASTA_TELEMETRIA_DETALHADA_ID)
    except RuntimeError as erro:
        print(f"AVISO: {erro} -- 2.1 fora desta rodada.")
        pacotes = None

    if os.path.exists(RESUMO_LOCAL):
        resumo = pd.read_csv(RESUMO_LOCAL)
        print(f"Resumo do 2.8 lido de {RESUMO_LOCAL}.")
    else:
        resumo = drive_io.ler_csv(servico, indicador_2_8_calculo.NOME_RESUMO, config.PASTA_RELATORIOS_ID)
        print("Resumo do 2.8 lido do Drive." if resumo is not None else "Resumo do 2.8 não encontrado.")

    log = {}
    print("\n=== Hidrologia -- Série histórica ===")
    log["Hidro série"] = paginas_hidrologia.gerar_hidro_serie(fato, dim, pacotes, caminho(config_cg.PAGINA_HIDRO_SERIE))
    print("\n=== Hidrologia -- Contrato de Gestão ===")
    log["Hidro CG"] = paginas_hidrologia.gerar_hidro_cg(fato, dim, pacotes, resumo, caminho(config_cg.PAGINA_HIDRO_CG))
    if RODAR_METEOROLOGIA:
        print("\n=== Meteorologia -- 2026 ===")
        log["Meteo 2026"] = meteorologia_cg.gerar_meteo_2026(caminho(config_cg.PAGINA_METEO_2026))
        print("\n=== Meteorologia -- Contrato de Gestão ===")
        log["Meteo CG"] = meteorologia_cg.gerar_meteo_cg(caminho(config_cg.PAGINA_METEO_CG))
        testar_busca_automatica_pasta()

    print("\n" + "=" * 60 + "\nRESUMO\n" + "=" * 60)
    for pagina, itens in log.items():
        print(pagina)
        for k, v in itens.items():
            print(f"  {k}: {v}")

    shutil.make_archive(PASTA_SAIDA, "zip", PASTA_SAIDA)
    print(f"\nPáginas em {PASTA_SAIDA}/ e {PASTA_SAIDA}.zip (nada foi gravado no Drive).")
    try:
        from google.colab import files
        files.download(f"{PASTA_SAIDA}.zip")
    except ImportError:
        pass


if __name__ == "__main__":
    main()
