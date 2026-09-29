"""
Descrição: ponto de entrada da execução diária de METEOROLOGIA via GitHub
Actions (pipeline_diario_meteoro.yml) -- extrai os indicadores 4.1, 4.2 e
4.3 do SIMGE e gera as DUAS páginas de Meteorologia no novo layout.

ATUALIZADO (27/09/2026 -- Contrato de Gestão + novo layout):
    meteorologia.html     -> visão "2026" (mesmo cálculo de antes)
    meteorologia_cg.html  -> visão "Contrato de Gestão" (desde 16/09/2026,
                             1 previsão por dia, sem desconto de feriados,
                             pasta do SIMGE de cada ano achada sozinha)
Os CSVs de 2026 no Drive continuam sendo gravados como antes.
Se a extração da visão 2026 falhar, a exceção sobe e a rodada falha (como
antes, para a quebra do SIMGE ser percebida rápido). Se só o Contrato de
Gestão falhar, a página 2026 é publicada mesmo assim (a falha fica no log).

Conexões do Pipeline:
- Entradas: chave de serviço (Secret); meteorologia_cg.py, config_cg.py,
  extrair_documentos_simge_*.py, drive_io.py.
- Saídas: meteorologia.html e meteorologia_cg.html (PASTA_SITE); CSVs de
  4.1/4.2/4.3 de 2026 no Drive.

Uso local (Colab/terminal):
    CAMINHO_CHAVE_JSON=minha_chave.json python rodar_diario_meteoro.py
"""
import os

CAMINHO_CHAVE = os.environ.get("CAMINHO_CHAVE_JSON", "chave_servico.json")
PASTA_SITE = os.environ.get("PASTA_SITE", "site_publicado")


def gerar_meteorologia(caminho_chave, pasta_site):
    import config
    import config_cg
    import drive_io
    import meteorologia_cg
    from extrair_documentos_simge_calculo import (
        dataframe_alertas_4_2,
        dataframe_dias_semana_4_1,
        dataframe_previsoes_4_1,
        dataframe_tendencia_4_3,
    )

    os.makedirs(pasta_site, exist_ok=True)

    # -- visão 2026 (e os CSVs do Drive, como antes) --
    resumo, r = meteorologia_cg.gerar_meteo_2026(
        os.path.join(pasta_site, config_cg.PAGINA_METEO_2026), devolver_resultados=True)
    print(resumo)
    servico = drive_io.conectar_drive(caminho_chave)
    drive_io.salvar_csv(servico, dataframe_previsoes_4_1(r["r_4_1"]),
                        "indicador_4_1_previsoes_2026.csv", config.PASTA_PREVISAO_TEMPO_ID)
    drive_io.salvar_csv(servico, dataframe_dias_semana_4_1(r["r_4_1"]),
                        "indicador_4_1_por_dia_semana_2026.csv", config.PASTA_PREVISAO_TEMPO_ID)
    drive_io.salvar_csv(servico, dataframe_tendencia_4_3(r["r_4_3"]),
                        "indicador_4_3_tendencia_climatica_2026.csv", config.PASTA_MONITORAMENTO_CLIMATICO_ID)
    drive_io.salvar_csv(servico, dataframe_alertas_4_2(r["r_4_2"]),
                        "indicador_4_2_alertas_2026.csv", config.PASTA_ALERTAS_METEOROLOGICOS_ID)

    # -- visão Contrato de Gestão --
    try:
        print(meteorologia_cg.gerar_meteo_cg(os.path.join(pasta_site, config_cg.PAGINA_METEO_CG)))
    except Exception as erro:  # noqa: BLE001 -- a visão 2026 já foi gerada e segue publicada
        print(f"ERRO na página do Contrato de Gestão ({type(erro).__name__}: {erro}) -- "
              "a página 2026 será publicada mesmo assim.")


def main():
    print("=== Meteorologia: SIMGE (4.1/4.2/4.3) + páginas 2026 e Contrato de Gestão ===")
    gerar_meteorologia(CAMINHO_CHAVE, PASTA_SITE)
    print("\nExecução diária de meteorologia concluída.")


if __name__ == "__main__":
    main()
