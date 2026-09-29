"""
Descrição: captação do MERGE (CPTEC/INPE) como referência de chuva para o
indicador 2.8, no lugar do CHIRPS (decisão de 28/09/2026 -- ver
decisoes_e_progresso.md, seção "Indicador 2.8 — troca da referência de
chuva: CHIRPS → MERGE"). AINDA NÃO chamado por indicador_2_8_calculo.py --
este módulo cobre a captação; a troca do CHIRPS pelo MERGE na tabela final
(colunas, rótulos, resumo) é um passo seguinte, depois deste ser testado.

Fonte: ftp.cptec.inpe.br/modelos/tempo/MERGE/GPM/DAILY/AAAA/MM/
  MERGE_CPTEC_AAAAMMDD.grib2 (~0,4-0,5 MB/dia; robots.txt inexistente,
  verificado em 28/09/2026 -- sem restrição declarada). Atraso de 0 dias
  (arquivo do próprio dia já publicado, ao menos nos testes de 28/09).
  Grade de 0,1°; banda 1 = PREC (chuva acumulada, mm, das 12 UTC do dia
  anterior às 12 UTC do dia -- confirmado no .ctl do produto, campo
  "tdef 1 linear 12Z<dia>2026 24hr").

Como funciona:
- Guarda os valores lidos num único CSV no Drive (NOME_ARQUIVO_CACHE, pasta
  informada em obter_chuva_merge -- pensado para ser config.PASTA_RELATORIOS_ID),
  uma linha por (codigo_estacao, data_dia) -- por SUBSTITUIÇÃO do arquivo
  inteiro a cada rodada (drive_io.salvar_csv, NÃO drive_io.acrescentar_linhas),
  para nunca duplicar linha quando o mesmo dia for lido de novo.
- A cada rodada, baixa e lê só: (a) os dias que ainda não estão completos
  no cache (faltando alguma estação), e (b) os últimos RELER_ULTIMOS_DIAS
  dias corridos, que são relidos mesmo já estando no cache -- o arquivo do
  dia pode ainda ser revisado pelo INPE logo após a publicação; isso NÃO
  foi confirmado com o INPE (a equipe decidiu não perguntar), então reler
  é a margem de segurança escolhida no lugar dessa confirmação.
- Nunca derruba a rodada: dia ainda não publicado (404) ou falha de rede
  faz essa data ficar de fora, e a função segue com o que conseguiu --
  mesmo padrão do Earth Engine/CHIRPS hoje (ver
  indicador_2_8_calculo.inicializar_earth_engine).

Conexões do Pipeline (uso previsto -- integração ao indicador_2_8_calculo
ainda pendente):
- Entradas: dim_estacao (codigo_estacao, latitude, longitude).
- Saídas: DataFrame codigo_estacao/data_dia/chuva_merge_mm; e o cache em
  si (NOME_ARQUIVO_CACHE) no Drive.

Dependência: rasterio -- NÃO está em requirements.txt ainda; adicionar
antes de usar em produção (pip install rasterio).
"""
import os
import time

import numpy as np
import pandas as pd
import requests

RAIZ_MERGE = "https://ftp.cptec.inpe.br/modelos/tempo/MERGE/GPM/DAILY/"
NOME_ARQUIVO_CACHE = "merge_chuva_diario.csv"
NOME_RELATORIO_FATO = "indicador_2_8_merge_fato.csv"  # estação x dia x satélite, reescrito a cada rodada
PASTA_LOCAL_GRIB = "merge_grib2_tmp"
RELER_ULTIMOS_DIAS = 5       # relê mesmo já estando no cache (revisão do INPE não confirmada)
TENTATIVAS = 3
ESPERA_ENTRE_TENTATIVAS_S = 2
TIMEOUT_S = 60
CABECALHO = {"User-Agent": "pipeline-igam-merge/1.0 (uso institucional; Sala de Situacao IGAM)"}
VALOR_MAX_VALIDO = 5000.0    # mm; acima disso trata como sem dado (arquivo corrompido/erro de leitura)
FUSO_ESTACAO_H = -3          # horário de Brasília (confirmado pela equipe, 28/09/2026)
LIMIAR_CHUVA_MM = 1.0


def _zf(serie):
    return serie.astype(str).str.strip().str.zfill(8)


def url_do_dia(dia):
    d = pd.Timestamp(dia)
    return f"{RAIZ_MERGE}{d.year}/{d.month:02d}/MERGE_CPTEC_{d:%Y%m%d}.grib2"


def _baixar(dia, pasta_local):
    os.makedirs(pasta_local, exist_ok=True)
    caminho = os.path.join(pasta_local, f"MERGE_CPTEC_{pd.Timestamp(dia):%Y%m%d}.grib2")
    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            r = requests.get(url_do_dia(dia), headers=CABECALHO, timeout=TIMEOUT_S)
            if r.status_code == 404:
                return None  # dia ainda não publicado -- esperado no dia corrente, não é erro
            r.raise_for_status()
            with open(caminho, "wb") as f:
                f.write(r.content)
            return caminho
        except Exception as erro:  # noqa: BLE001
            ultimo_erro = erro
            time.sleep(ESPERA_ENTRE_TENTATIVAS_S * tentativa)
    print(f"  AVISO: MERGE de {pd.Timestamp(dia).date()} falhou após {TENTATIVAS} tentativas "
          f"({type(ultimo_erro).__name__}: {ultimo_erro}).")
    return None


def _extrair_pontos(caminho_grib2, df_coord):
    """Valor do pixel de cada estação (banda 1 = PREC). df_coord precisa
    ter codigo_estacao, latitude, longitude, nessa ordem de uso."""
    import rasterio
    lons = df_coord["longitude"].astype(float).values
    lats = df_coord["latitude"].astype(float).values
    with rasterio.open(caminho_grib2) as src:
        lons_uso = np.where((src.bounds.left >= 0) & (lons < 0), lons + 360.0, lons)
        amostras = src.sample(list(zip(lons_uso, lats)), indexes=[1], masked=True)
        valores = [np.ma.filled(v, np.nan)[0] for v in amostras]
    valores = np.array(valores, dtype="float64")
    valores[(valores < 0) | (valores > VALOR_MAX_VALIDO)] = np.nan
    return valores


def _ler_um_dia(dia, df_coord, pasta_local):
    caminho = _baixar(dia, pasta_local)
    if caminho is None:
        return None
    try:
        valores = _extrair_pontos(caminho, df_coord)
    except Exception as erro:  # noqa: BLE001
        print(f"  AVISO: falha ao ler o GRIB2 de {pd.Timestamp(dia).date()} ({type(erro).__name__}: {erro}).")
        return None
    finally:
        try:
            os.remove(caminho)   # só os pontos extraídos importam; não precisa guardar o arquivo bruto
        except OSError:
            pass
    return pd.DataFrame({"codigo_estacao": df_coord["codigo_estacao"].values, "data_dia": pd.Timestamp(dia),
                         "chuva_merge_mm": valores})


def obter_chuva_merge(df_coord, data_inicio, data_fim, servico=None, pasta_id=None,
                      salvar_no_drive=True, pasta_local=PASTA_LOCAL_GRIB):
    """DataFrame codigo_estacao/data_dia/chuva_merge_mm para [data_inicio, data_fim].

    Usa o cache do Drive (NOME_ARQUIVO_CACHE) quando servico E pasta_id são
    informados; sem eles, baixa tudo do zero (uso em teste/Colab sem Drive).
    salvar_no_drive=False lê o cache normalmente mas NUNCA grava -- usar em
    testes. Nunca levanta exceção: na pior das hipóteses devolve só o que
    já estava em cache (ou vazio), e quem chama decide o que fazer (mesmo
    espírito do inicializar_earth_engine, que devolve False em vez de
    quebrar a rodada)."""
    import drive_io
    df_coord = df_coord.copy()
    df_coord["codigo_estacao"] = _zf(df_coord["codigo_estacao"])
    df_coord = df_coord.dropna(subset=["latitude", "longitude"]).drop_duplicates("codigo_estacao")

    cache = pd.DataFrame({"codigo_estacao": pd.array([], dtype="string"),
                          "data_dia": pd.array([], dtype="datetime64[ns]"),
                          "chuva_merge_mm": pd.array([], dtype="float64")})
    if servico is not None and pasta_id is not None:
        try:
            lido = drive_io.ler_csv(servico, NOME_ARQUIVO_CACHE, pasta_id)
            if lido is not None and not lido.empty:
                lido["codigo_estacao"] = _zf(lido["codigo_estacao"])
                lido["data_dia"] = pd.to_datetime(lido["data_dia"])
                cache = lido[["codigo_estacao", "data_dia", "chuva_merge_mm"]]
        except Exception as erro:  # noqa: BLE001
            print(f"  AVISO: erro ao ler {NOME_ARQUIVO_CACHE} do Drive ({erro}) -- começando do zero.")

    todos_dias = list(pd.date_range(data_inicio, data_fim))
    ja_no_cache = set(zip(cache["codigo_estacao"], cache["data_dia"])) if len(cache) else set()
    estacoes = set(df_coord["codigo_estacao"])
    dias_completos = {d for d in todos_dias if estacoes and all((c, d) in ja_no_cache for c in estacoes)}
    limite_releitura = pd.Timestamp(data_fim) - pd.Timedelta(days=RELER_ULTIMOS_DIAS - 1)
    dias_para_ler = sorted(d for d in todos_dias if d not in dias_completos or d >= limite_releitura)

    print(f"  MERGE: {len(dias_para_ler)} dia(s) a (re)ler de {len(todos_dias)} no período "
          f"({len(todos_dias) - len(dias_para_ler)} já em cache e fora da janela de releitura).")
    novos = []
    for dia in dias_para_ler:
        resultado = _ler_um_dia(dia, df_coord, pasta_local)
        if resultado is not None:
            novos.append(resultado)

    if not novos and cache.empty:
        print("  AVISO: nenhum dia do MERGE pôde ser lido -- comparação fica indisponível nesta rodada.")
        return pd.DataFrame(columns=["codigo_estacao", "data_dia", "chuva_merge_mm"])

    novo_df = (pd.concat(novos, ignore_index=True) if novos
               else pd.DataFrame(columns=["codigo_estacao", "data_dia", "chuva_merge_mm"]))
    combinado = pd.concat([cache, novo_df], ignore_index=True)
    combinado["data_dia"] = pd.to_datetime(combinado["data_dia"])  # concat com cache vazio pode virar object
    combinado = combinado.drop_duplicates(["codigo_estacao", "data_dia"], keep="last")

    if servico is not None and pasta_id is not None and salvar_no_drive and novos:
        n_chaves = len(set(zip(combinado["codigo_estacao"], combinado["data_dia"])))
        if n_chaves != len(combinado):
            print("  ERRO: chave (estação, dia) duplicada no MERGE -- NÃO gravando no Drive, para não arriscar "
                  "sobrescrever com dado errado. Confira manualmente antes da próxima rodada.")
        else:
            try:
                drive_io.salvar_csv(servico, combinado, NOME_ARQUIVO_CACHE, pasta_id)
                print(f"  MERGE: cache atualizado no Drive ({len(combinado)} estação-dias).")
            except Exception as erro:  # noqa: BLE001
                print(f"  AVISO: falha ao salvar {NOME_ARQUIVO_CACHE} no Drive ({erro}) -- "
                      "os novos valores valem só para esta rodada.")

    intervalo = (combinado["data_dia"] >= pd.Timestamp(data_inicio)) & (combinado["data_dia"] <= pd.Timestamp(data_fim))
    return combinado[intervalo].sort_values(["codigo_estacao", "data_dia"]).reset_index(drop=True)


def agregar_chuva_12z(df_input, fuso_estacao_h=FUSO_ESTACAO_H):
    """Soma a chuva de cada leitura na janela 12Z-12Z (12 UTC do dia
    anterior às 12 UTC do dia rotulado) -- a janela que o MERGE usa. É a
    soma correta para comparar com o MERGE; a soma por dia do calendário
    (etapa01_teste_chuva.agregar_chuva_diaria) SUBESTIMA a concordância
    (~91-92% x ~97-98%, medido em 28/09/2026)."""
    df = df_input.copy()
    df["codigo_estacao"] = _zf(df["codigo_estacao"])
    if not pd.api.types.is_datetime64_any_dtype(df["data_hora"]):
        df["data_hora"] = pd.to_datetime(df["data_hora"])
    deslocado = df["data_hora"] - pd.Timedelta(hours=fuso_estacao_h + 12)
    df["data_dia"] = deslocado.dt.normalize() + pd.Timedelta(days=1)

    diario = (df.groupby(["codigo_estacao", "data_dia"])
                .agg(chuva_12z_mm=("chuva", "sum"), n_leituras=("chuva", "count"))
                .reset_index())
    diario.loc[diario["n_leituras"] == 0, "chuva_12z_mm"] = np.nan
    return diario.drop(columns="n_leituras")


def comparar_com_merge(df_12z, df_merge, limiar=LIMIAR_CHUVA_MM):
    """Mesma lógica de etapa01_teste_chuva.comparar_com_chirps, com o
    MERGE no lugar do CHIRPS e a estação somada na janela 12Z-12Z."""
    df = df_12z.merge(df_merge, on=["codigo_estacao", "data_dia"], how="left")
    estacao_choveu = df["chuva_12z_mm"] > limiar
    merge_choveu = df["chuva_merge_mm"] > limiar
    tem_ambos = df["chuva_12z_mm"].notna() & df["chuva_merge_mm"].notna()
    df["divergencia_merge"] = np.where(tem_ambos, estacao_choveu != merge_choveu, np.nan)
    return df[["codigo_estacao", "data_dia", "chuva_12z_mm", "chuva_merge_mm", "divergencia_merge"]]


def propagar_comparacao_merge_para_leituras(df_leitura, df_comparacao_12z, fuso_estacao_h=FUSO_ESTACAO_H):
    """Espalha o resultado da comparação com o MERGE (calculada por janela
    12Z-12Z, ver agregar_chuva_12z) para cada LEITURA que cai nessa janela --
    equivalente a etapa01_teste_chuva.propagar_comparacao_chirps_para_leituras,
    mas juntando pela janela 12Z-12Z, não pelo dia do calendário."""
    df = df_leitura.copy()
    df["codigo_estacao"] = _zf(df["codigo_estacao"])
    if not pd.api.types.is_datetime64_any_dtype(df["data_hora"]):
        df["data_hora"] = pd.to_datetime(df["data_hora"])
    deslocado = df["data_hora"] - pd.Timedelta(hours=fuso_estacao_h + 12)
    df["data_dia"] = deslocado.dt.normalize() + pd.Timedelta(days=1)
    return df.merge(df_comparacao_12z, on=["codigo_estacao", "data_dia"], how="left")
