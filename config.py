"""
Descrição: constantes fixas do projeto -- IDs das pastas do Google Drive
usadas por todo o pipeline.

Conexões do Pipeline:
- Entradas: nenhuma.
- Saídas: importado por todos os módulos que leem/gravam no Drive
  (drive_io, orquestrador, pipeline_consistencia, indicador_2_2_calculo,
  extrair_documentos_simge_calculo, rodar_diario_hidro, rodar_diario_meteoro,
  gerar_relatorios_visuais).

Funções: nenhuma (apenas constantes).
"""

PASTA_DATA_ID = "1RKiSuOL8-4zuJGDpFnSA4YG-iWgAi4D1"
PASTA_ESTACOES_ID = "19h0NtwSYnX8KBgug4Mwkr7-8TnZHL7rL"
PASTA_RELATORIOS_ID = "1VA8cMwIxuWRt87jbXdKM_7mIxzm5Z_rn"
PASTA_ESTACOES_FLAGS_ID = "15Rie6x1JG8j-0Ye67mxLYmMDr3kO2sjo"

# Pastas de saida dos indicadores 4.x (SIMGE) -- adicionadas em 31/08.
PASTA_PREVISAO_TEMPO_ID = "1laGiZKDKCLGdn0RV9ex3Z9Rdn9sF682L"  # indicador 4.1
PASTA_MONITORAMENTO_CLIMATICO_ID = "1qlIrmrxbr7f9kyAU1bCMNubuN6WMXZ_c"  # indicador 4.3
PASTA_ALERTAS_METEOROLOGICOS_ID = "1VZF9AcAJcblwKO3-_0dXkT-hTFeS0ekc"  # indicador 4.2

# Pasta unica pra guardar os graficos/paginas gerados (PNGs do indicador 2.2 e os HTML do site: index.html/meteorologia.html)
PASTA_GRAFICOS_ID = "1DCHsoCOxF1XMVex9A3zYC5s9MUJkFm1c"

# Pasta com os estacao_detalhada_XXXXXXXX.csv da API nova (HidroWebService,
# rota Detalhada) -- indicador 2.1. Grao leitura x estacao, alimentada pela
# captura incremental (~30 dias rolantes). Adicionada em 09/09.
PASTA_TELEMETRIA_DETALHADA_ID = "1KYFVvN81s3mQfLNDaQpzuvxK4ls1T9Jy"