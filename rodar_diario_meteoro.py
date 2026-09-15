"""
Descrição: ponto de entrada da execução diária de METEOROLOGIA via GitHub
Actions (pipeline_diario_meteoro.yml) -- extrai os indicadores 4.1, 4.2 e
4.3 do SIMGE, gera meteorologia.html e salva os CSVs no Drive. Roda numa
Action separada da hidrometria: se a extração do SIMGE falhar, a exceção
sobe e só esta rodada falha (sem "avisa e pula" como na Fase 5 de
hidrometria), para que a quebra seja percebida rápido.

Conexões do Pipeline:
- Entradas: chave de serviço (Secret do GitHub); usa
  extrair_documentos_simge_ingestao.py, extrair_documentos_simge_calculo.py,
  indicador_meteorologia.py, nav_site.py, drive_io.py.
- Saídas: meteorologia.html (CAMINHO_METEOROLOGIA_SAIDA), publicado no
  repositório público do dashboard; CSVs de 4.1/4.2/4.3 no Drive
  (config.PASTA_PREVISAO_TEMPO_ID, config.PASTA_MONITORAMENTO_CLIMATICO_ID,
  config.PASTA_ALERTAS_METEOROLOGICOS_ID).

Funções:
- gerar_meteorologia: extrai os indicadores, gera o HTML e salva os CSVs no Drive.
- main: executa gerar_meteorologia() com as configurações padrão.

Uso local (Colab/terminal), se quiser rodar a sequência completa manualmente:
    CAMINHO_CHAVE_JSON=minha_chave.json python rodar_diario_meteoro.py
Sem a variável de ambiente definida, usa "chave_servico.json" como padrão
(nome que o workflow do GitHub Actions grava).

Para testar só a geração da página (sem salvar no Drive) no Colab, antes de
confiar nela dentro do workflow real:

    from datetime import date
    from extrair_documentos_simge_ingestao import (
        URL_PASTA_PREVISOES_2026, URL_PASTA_TENDENCIA_CLIMATICA_2026, URL_ALERTAS_TEMPESTADE_SEVERA,
    )
    from extrair_documentos_simge_calculo import (
        contar_previsoes_4_1, contar_tendencia_climatica_4_3, contar_alertas_4_2,
        calcular_cd_4_1, calcular_cd_4_3, calcular_cd_4_2,
    )
    from indicador_meteorologia import gerar_html_meteorologia
    from nav_site import injetar_nav

    data_inicio, hoje = "2026-01-01", date.today()
    r_4_1 = contar_previsoes_4_1(URL_PASTA_PREVISOES_2026, data_inicio, hoje)
    r_4_3 = contar_tendencia_climatica_4_3(URL_PASTA_TENDENCIA_CLIMATICA_2026, data_inicio, hoje)
    r_4_2 = contar_alertas_4_2(URL_ALERTAS_TEMPESTADE_SEVERA, data_inicio, hoje)
    cd_4_1 = calcular_cd_4_1(r_4_1, data_inicio, hoje)
    cd_4_3 = calcular_cd_4_3(r_4_3, data_inicio, hoje)
    cd_4_2 = calcular_cd_4_2(r_4_2, data_inicio, hoje)
    gerar_html_meteorologia(
        r_4_1, r_4_3, "meteorologia_teste.html",
        resultado_cd_4_1=cd_4_1, resultado_cd_4_3=cd_4_3,
        resultado_4_2=r_4_2, resultado_cd_4_2=cd_4_2,
    )
    injetar_nav("meteorologia_teste.html", "meteorologia")
    # abra meteorologia_teste.html no navegador (ou baixe do Colab) pra
    # conferir antes de deixar o workflow publicar de verdade.
"""
import os
from datetime import date

CAMINHO_CHAVE = os.environ.get("CAMINHO_CHAVE_JSON", "chave_servico.json")
CAMINHO_METEOROLOGIA_SAIDA = os.environ.get(
    "CAMINHO_METEOROLOGIA_SAIDA", "site_publicado/meteorologia.html"
)

# Data de inicio da serie 2026 -- mesma usada em extrair_documentos_simge_ingestao.py
# e em gerar_relatorios_visuais.py (Colab). Ajuste aqui se um dia a serie
# precisar comecar em outro ano.
DATA_INICIO_SERIE = "2026-01-01"


def gerar_meteorologia(caminho_chave, caminho_saida):
    """Extrai os indicadores 4.1/4.2/4.3 do SIMGE, calcula a pontuação
    (CD) de cada um, gera meteorologia.html (com a barra de navegação) em
    caminho_saida e salva os CSVs de 4.1/4.2/4.3 no Drive."""
    import config
    import drive_io
    from extrair_documentos_simge_ingestao import (
        URL_PASTA_PREVISOES_2026,
        URL_PASTA_TENDENCIA_CLIMATICA_2026,
        URL_ALERTAS_TEMPESTADE_SEVERA,
    )
    from extrair_documentos_simge_calculo import (
        contar_previsoes_4_1,
        contar_tendencia_climatica_4_3,
        contar_alertas_4_2,
        calcular_cd_4_1,
        calcular_cd_4_3,
        calcular_cd_4_2,
        dataframe_previsoes_4_1,
        dataframe_dias_semana_4_1,
        dataframe_tendencia_4_3,
        dataframe_alertas_4_2,
    )
    from indicador_meteorologia import gerar_html_meteorologia
    from nav_site import injetar_nav

    hoje = date.today()

    r_4_1 = contar_previsoes_4_1(URL_PASTA_PREVISOES_2026, DATA_INICIO_SERIE, hoje)
    r_4_3 = contar_tendencia_climatica_4_3(URL_PASTA_TENDENCIA_CLIMATICA_2026, DATA_INICIO_SERIE, hoje)
    r_4_2 = contar_alertas_4_2(URL_ALERTAS_TEMPESTADE_SEVERA, DATA_INICIO_SERIE, hoje)  # novo (02/09)

    cd_4_1 = calcular_cd_4_1(r_4_1, DATA_INICIO_SERIE, hoje)
    cd_4_3 = calcular_cd_4_3(r_4_3, DATA_INICIO_SERIE, hoje)
    cd_4_2 = calcular_cd_4_2(r_4_2, DATA_INICIO_SERIE, hoje)  # novo (02/09)

    pasta_saida = os.path.dirname(caminho_saida)
    if pasta_saida:
        os.makedirs(pasta_saida, exist_ok=True)

    gerar_html_meteorologia(
        r_4_1, r_4_3, caminho_saida,
        resultado_cd_4_1=cd_4_1, resultado_cd_4_3=cd_4_3,
        resultado_4_2=r_4_2, resultado_cd_4_2=cd_4_2,
    )
    injetar_nav(caminho_saida, "meteorologia")

    servico = drive_io.conectar_drive(caminho_chave)
    drive_io.salvar_csv(
        servico, dataframe_previsoes_4_1(r_4_1),
        "indicador_4_1_previsoes_2026.csv", config.PASTA_PREVISAO_TEMPO_ID,
    )
    drive_io.salvar_csv(
        servico, dataframe_dias_semana_4_1(r_4_1),
        "indicador_4_1_por_dia_semana_2026.csv", config.PASTA_PREVISAO_TEMPO_ID,
    )
    drive_io.salvar_csv(
        servico, dataframe_tendencia_4_3(r_4_3),
        "indicador_4_3_tendencia_climatica_2026.csv", config.PASTA_MONITORAMENTO_CLIMATICO_ID,
    )
    drive_io.salvar_csv(
        servico, dataframe_alertas_4_2(r_4_2),
        "indicador_4_2_alertas_2026.csv", config.PASTA_ALERTAS_METEOROLOGICOS_ID,
    )  # novo (02/09)


def main():
    print("=== Meteorologia: extração SIMGE (4.1/4.3) + página do site ===")
    gerar_meteorologia(CAMINHO_CHAVE, CAMINHO_METEOROLOGIA_SAIDA)
    print("\nExecução diária de meteorologia concluída.")


if __name__ == "__main__":
    main()
