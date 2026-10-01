"""
Descrição: indicador 2.8 -- Consistência de Dados. Aplica os testes da
pasta indicador_2_8 (chuva: valor impossível pelo acumulado mensal +
comparação diária com CHIRPS; nível: Range + Persist regional) às
leituras do período do Contrato de Gestão, e calcula o resultado e a
nota (CD) conforme o Anexo II.

Regras (decididas com a Valéria/chefia -- ver decisoes_e_progresso.md):
- Período: config_cg.DATA_INICIO_CG_HIDRO até a data da rodada.
- Universo CHUVA: estações com dado no período, com tem_chuva=True e fora
  de config_cg.ESTACOES_EXCLUIDAS_CHUVA (5 desinstaladas).
- Universo NÍVEL: estações com dado no período, com tem_cota=True (as só
  pluviométricas ficam FORA -- decisão de 27/09) e fora de
  config_cg.ESTACOES_EXCLUIDAS_NIVEL (8 desinstaladas).
- Estação SEM nenhuma leitura no período não entra nos testes (vai para
  a lista de "sem dado", como no rodar_colab_indicador_2_8.py).
- NOTA (CD) -- decisão de 27/09, texto do Anexo II ("dados consistidos ÷
  dados coletados"), SOMA DA REDE:
    coletadas  = leituras que chegaram com valor (em branco não é dado
                 coletado; a falta de dado já é cobrada no 2.2);
    consistidas = coletadas que receberam resultado final da consistência
                 (aprovadas OU reprovadas).
  Não consistidas = leituras com valor que não foram testadas (lacuna na
  janela do Persist; Persist sem cálculo). Medidas chuva_cd e nivel_cd.
- QUALIDADE (gráficos aprovado × reprovado, sem nota) -- "tudo na base"
  (orientação da chefia, 27/09): leitura em branco ("nulo"), "suspeito" e
  "Teste não realizado" contam como reprovadas. Medidas chuva,
  nivel_range e nivel_final.
- Nível -- resultado final: leitura aprovada no Range E no Persist (como o
  Persist só roda quando o Range aprova, basta status_nivel_persist ==
  "aprovado"). O Range sozinho também é resumido, só para exibição.
- Nota (Anexo II, 2.8): >=95% -> 10; 90-94,99 -> 9; 80-89,99 -> 8; <80 -> 0.
  Uma nota para CHUVA e outra para NÍVEL.
- Comparação com satélite: informativa, não entra na nota. Até 27/09
  usava o CHIRPS (Earth Engine); desde 28/09/2026 usa o MERGE (CPTEC/INPE,
  captacao_merge.py) -- ver decisoes_e_progresso.md, "Indicador 2.8 --
  troca da referência de chuva: CHIRPS -> MERGE". Se o MERGE não puder ser
  lido, a rodada segue sem ele (divergencia_merge vazia) e o resumo
  registra merge_status="indisponível". aplicar_chirps/_contar_chirps
  continuam no código, dormentes, caso seja preciso voltar atrás.

Conexões do Pipeline:
- Entradas: leituras de cada estação (df já lido por pipeline_consistencia),
  dim_estacao.csv, valores_min_max.csv (Drive, config.PASTA_DATA_ID; se não
  achar, procura na pasta local; se não achar, Range só por z-score).
  Usa etapa01_teste_chuva.py, etapa_range_cota_zscore.py e
  etapa03_persist_regional.py (pasta indicador_2_8, SEM alteração).
- Saídas (config.PASTA_RELATORIOS_ID, reescritos a cada rodada):
  indicador_2_8_resumo.csv (1 linha por medida, com a nota),
  indicador_2_8_por_estacao.csv (mesmas medidas por estação),
  indicador_2_8_leituras.parquet (tabela completa por leitura -- a mesma
  do indicador_2_8_bruto.csv do Colab).
"""
import os

import numpy as np
import pandas as pd

import config
import config_cg
import drive_io
import captacao_merge
import etapa01_teste_chuva as chuva
import etapa03_persist_regional as persist
import etapa_range_cota_zscore as range_cota

NOME_RESUMO = "indicador_2_8_resumo.csv"
NOME_POR_ESTACAO = "indicador_2_8_por_estacao.csv"
NOME_LEITURAS = "indicador_2_8_leituras.parquet"
NOME_MIN_MAX = "valores_min_max.csv"
PROJETO_EARTH_ENGINE = os.environ.get("EE_PROJECT") or "priorizacao-estacoes"

# Janela padrão do Persist vem do config_cg (fonte de verdade única para mudar o
# valor de produção). etapa03_persist_regional.py já traz 96 como próprio padrão
# (correção de 29/09/2026); esta linha só garante que os dois nunca fiquem
# diferentes, mesmo que um dos dois mude no futuro.
persist.JANELA_PADRAO_FALLBACK = config_cg.JANELA_PERSIST_PADRAO


# ---------------------------------------------------------------------
# Nota
# ---------------------------------------------------------------------
TABELA_CD_2_8 = [(95.0, 10), (90.0, 9), (80.0, 8), (0.0, 0)]  # Anexo II -- sem faixa 7


def nota_2_8(percentual):
    if percentual is None or pd.isna(percentual):
        return None
    for limite, pontos in TABELA_CD_2_8:
        if percentual >= limite:
            return pontos
    return 0


# ---------------------------------------------------------------------
# Entradas auxiliares
# ---------------------------------------------------------------------
def _eh_verdadeiro(serie):
    return serie.astype(str).str.strip().str.lower().isin({"true", "1", "sim", "s"})


def preparar_dim(dim_estacao):
    dim = dim_estacao.copy()
    dim["codigo_estacao"] = dim["codigo_estacao"].astype(str).str.zfill(8)
    dim["_tem_chuva"] = _eh_verdadeiro(dim["tem_chuva"]) if "tem_chuva" in dim else True
    dim["_tem_cota"] = _eh_verdadeiro(dim["tem_cota"]) if "tem_cota" in dim else True
    return dim


ALIASES_COD_MIN_MAX = ["cod_estacao", "codigo_estacao", "codigo_frente1_proposto", "cod_estacao_planilha"]


def _numero_br(serie):
    """Aceita 110 / 110.5 / 110,5 / 1.200,5 (Excel em português)."""
    txt = serie.astype(str).str.strip()
    tem_virgula = txt.str.contains(",", regex=False)
    txt = txt.where(~tem_virgula, txt.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(txt, errors="coerce")


def carregar_valores_min_max(servico):
    """Drive (PASTA_DATA_ID) -> arquivo local -> vazio (Range só por z-score).
    30/09/2026: aceita separador ',' ou ';' (Excel em português salva com ';'),
    decimal com vírgula e BOM; se as colunas não baterem, avisa e segue só com
    o z-score em vez de derrubar a Fase 4."""
    vazio = pd.DataFrame(columns=["cod_estacao", "minimo", "maximo"])
    df = None
    try:
        df = drive_io.ler_csv(servico, NOME_MIN_MAX, config.PASTA_DATA_ID)
        if df is not None and len(df.columns) == 1 and ";" in str(df.columns[0]):
            df = drive_io.ler_csv(servico, NOME_MIN_MAX, config.PASTA_DATA_ID, sep=";")
    except Exception as erro:  # noqa: BLE001
        print(f"  AVISO: erro ao ler {NOME_MIN_MAX} do Drive ({erro}).")
    if df is None and os.path.exists(NOME_MIN_MAX):
        df = pd.read_csv(NOME_MIN_MAX, sep=None, engine="python", encoding="utf-8-sig")
        print(f"  {NOME_MIN_MAX} lido da pasta local.")
    if df is None:
        print(f"  AVISO: {NOME_MIN_MAX} não encontrado -- Range só por z-score nesta rodada.")
        return vazio

    df.columns = [str(c).replace("\ufeff", "").strip().lower() for c in df.columns]
    df = df.rename(columns={"min": "minimo", "max": "maximo", "mínimo": "minimo", "máximo": "maximo"})
    col_cod = next((c for c in ALIASES_COD_MIN_MAX if c in df.columns), None)
    if col_cod is None or "minimo" not in df.columns or "maximo" not in df.columns:
        print(f"  AVISO: {NOME_MIN_MAX} sem as colunas esperadas (cod_estacao, minimo, maximo). "
              f"Colunas encontradas: {list(df.columns)} -- Range só por z-score nesta rodada.")
        return vazio

    df = df.rename(columns={col_cod: "cod_estacao"})[["cod_estacao", "minimo", "maximo"]]
    df["cod_estacao"] = (df["cod_estacao"].astype(str).str.strip()
                         .str.replace(r"\.0$", "", regex=True).str.zfill(8))
    df["minimo"] = _numero_br(df["minimo"])
    df["maximo"] = _numero_br(df["maximo"])
    df = df[df["cod_estacao"].str.fullmatch(r"\d{8}") & df["minimo"].notna() & df["maximo"].notna()]
    print(f"  {NOME_MIN_MAX}: {len(df)} estações com mínimo/máximo "
          f"(mínimo de {df['minimo'].min()} a {df['minimo'].max()}; máximo de {df['maximo'].min()} a {df['maximo'].max()}).")
    return df


def inicializar_earth_engine(caminho_chave):
    """Tenta, nesta ordem: conta de serviço (chave JSON do pipeline) e login
    já feito na sessão (Colab, ee.Authenticate()). Devolve True/False --
    nunca derruba a rodada."""
    try:
        import ee
    except ImportError:
        print("  AVISO: earthengine-api não instalado -- CHIRPS fica de fora.")
        return False
    try:
        import json
        with open(caminho_chave, encoding="utf-8") as f:
            email = json.load(f)["client_email"]
        credenciais = ee.ServiceAccountCredentials(email, caminho_chave)
        ee.Initialize(credenciais, project=PROJETO_EARTH_ENGINE)
        print(f"  Earth Engine: conta de serviço ({email}), projeto {PROJETO_EARTH_ENGINE}.")
        return True
    except Exception as erro_sa:  # noqa: BLE001
        try:
            ee.Initialize(project=PROJETO_EARTH_ENGINE)
            print(f"  Earth Engine: login da sessão, projeto {PROJETO_EARTH_ENGINE} "
                  f"(conta de serviço falhou: {type(erro_sa).__name__}).")
            return True
        except Exception as erro:  # noqa: BLE001
            print(f"  AVISO: Earth Engine indisponível ({type(erro).__name__}: {erro}) -- CHIRPS fica de fora.")
            return False


# ---------------------------------------------------------------------
# Testes por estação
# ---------------------------------------------------------------------
def recortar_periodo(df_estacao, data_fim):
    df = df_estacao.copy()
    df["codigo_estacao"] = df["codigo_estacao"].astype(str).str.zfill(8)
    if not pd.api.types.is_datetime64_any_dtype(df["data_hora"]):
        df["data_hora"] = pd.to_datetime(df["data_hora"])
    fim = pd.Timestamp(data_fim) + pd.Timedelta(days=1)
    return df[(df["data_hora"] >= pd.Timestamp(config_cg.DATA_INICIO_CG_HIDRO)) & (df["data_hora"] < fim)]


def universo_da_estacao(codigo, dim):
    """(entra_chuva, entra_nivel) para uma estação, pelas regras do módulo."""
    linha = dim[dim["codigo_estacao"] == codigo]
    tem_chuva = bool(linha["_tem_chuva"].iloc[0]) if not linha.empty else True
    tem_cota = bool(linha["_tem_cota"].iloc[0]) if not linha.empty else False
    entra_chuva = tem_chuva and codigo not in config_cg.ESTACOES_EXCLUIDAS_CHUVA
    entra_nivel = tem_cota and codigo not in config_cg.ESTACOES_EXCLUIDAS_NIVEL
    return entra_chuva, entra_nivel


def testar_chuva(df_periodo):
    """status_chuva (acumulado mensal) por leitura -- etapa01_teste_chuva."""
    return chuva.teste_valores_impossiveis_chuva(df_periodo)


def testar_nivel(df_periodo, df_min_max, df_regiao):
    """Range + Persist por leitura -- devolve a tabela de nível (montar_tabela_cota)."""
    df_gap = range_cota.calcular_gap_leitura(df_periodo)
    df_range = range_cota.teste_range_zscore(df_gap, df_min_max)
    df_persist = persist.teste_persistencia_regional(df_range, df_regiao_estacao=df_regiao)
    return persist.montar_tabela_cota(df_persist)


def aplicar_chirps(dfs_chuva, dim, data_fim, ee_ok):
    """RESERVA/DORMANT desde 28/09/2026 -- substituída por aplicar_merge()
    na chamada real (ver pipeline_consistencia.py e decisoes_e_progresso.md,
    "Indicador 2.8 -- troca da referência de chuva: CHIRPS -> MERGE").
    Mantida aqui sem alteração, caso seja preciso voltar ao CHIRPS."""
    colunas_comp = ["codigo_estacao", "data_dia", "chuva_diaria_mm", "chirps_dia", "divergencia_chuva"]
    df_comparacao = pd.DataFrame(columns=colunas_comp)
    if ee_ok and dfs_chuva:
        diarios = pd.concat([chuva.agregar_chuva_diaria(d) for d in dfs_chuva.values()], ignore_index=True)
        dim_coord = dim[dim["codigo_estacao"].isin(dfs_chuva.keys())].dropna(subset=["latitude", "longitude"])
        try:
            df_chirps = chuva.extrair_chirps_diario(
                dim_coord, config_cg.DATA_INICIO_CG_HIDRO, str(pd.Timestamp(data_fim) + pd.Timedelta(days=1))[:10]
            )
            df_comparacao = chuva.comparar_com_chirps(diarios, df_chirps)
        except Exception as erro:  # noqa: BLE001
            print(f"  AVISO: extração do CHIRPS falhou ({type(erro).__name__}: {erro}) -- seguindo sem ele.")
    tabelas = []
    for df_status in dfs_chuva.values():
        df_final = chuva.propagar_comparacao_chirps_para_leituras(df_status, df_comparacao)
        tabelas.append(chuva.montar_tabela_chuva(df_final))
    return pd.concat(tabelas, ignore_index=True) if tabelas else pd.DataFrame()


def aplicar_merge(dfs_chuva, dim, data_fim, servico, salvar_no_drive=True):
    """Compara a chuva das estações com o MERGE (CPTEC/INPE), se disponível,
    e devolve a tabela de chuva por leitura -- SUBSTITUI aplicar_chirps()
    na chamada real (decisão de 28/09/2026, ver decisoes_e_progresso.md).

    A soma da estação usa a janela 12Z-12Z (captacao_merge.agregar_chuva_12z),
    a mesma que o MERGE usa -- a soma por dia do calendário SUBESTIMA a
    concordância (~91-92% x ~97-98%, medido em 28/09/2026).

    `salvar_no_drive` controla só a gravação do CACHE do MERGE
    (captacao_merge.NOME_ARQUIVO_CACHE); passar salvar_no_drive=False em
    testes no Colab para não gravar nada de verdade.

    Devolve (tabela_chuva, merge_ok, fato): `fato` é a tabela estação-dia
    usada na comparação (codigo_estacao/data_dia/chuva_12z_mm/
    chuva_merge_mm/divergencia_merge), pensada para ser salva como
    relatório (captacao_merge.NOME_RELATORIO_FATO) por quem chama; None se
    o MERGE não pôde ser lido nesta rodada (não passou a checagem de
    merge_ok)."""
    colunas_comp = ["codigo_estacao", "data_dia", "chuva_12z_mm", "chuva_merge_mm", "divergencia_merge"]
    fato = pd.DataFrame(columns=colunas_comp)
    merge_ok = False
    if dfs_chuva:
        df_12z = pd.concat([captacao_merge.agregar_chuva_12z(d) for d in dfs_chuva.values()], ignore_index=True)
        dim_coord = dim[dim["codigo_estacao"].isin(dfs_chuva.keys())].dropna(subset=["latitude", "longitude"])
        try:
            df_merge = captacao_merge.obter_chuva_merge(
                dim_coord, config_cg.DATA_INICIO_CG_HIDRO, data_fim, servico=servico,
                pasta_id=config.PASTA_RELATORIOS_ID, salvar_no_drive=salvar_no_drive)
            if df_merge is not None and not df_merge.empty:
                fato = captacao_merge.comparar_com_merge(df_12z, df_merge)
                merge_ok = True
        except Exception as erro:  # noqa: BLE001
            print(f"  AVISO: comparação com o MERGE falhou ({type(erro).__name__}: {erro}) -- seguindo sem ela.")
    tabelas = []
    for df_status in dfs_chuva.values():
        df_final = captacao_merge.propagar_comparacao_merge_para_leituras(df_status, fato)
        tabelas.append(chuva.montar_tabela_chuva(df_final))
    tabela_chuva = pd.concat(tabelas, ignore_index=True) if tabelas else pd.DataFrame()
    return tabela_chuva, merge_ok, fato


# ---------------------------------------------------------------------
# Resumo (soma da rede) e nota
# ---------------------------------------------------------------------
RESULTADO_FINAL_CHUVA = {"aprovado", "reprovado"}
RESULTADO_FINAL_RANGE_SEM_PERSIST = {"reprovado", "suspeito"}  # o Range deu o veredito; o Persist não roda
RESULTADO_FINAL_PERSIST = {"aprovado", "reprovado"}


def _medidas(tabela):
    """Contagens da rede (ou de uma estação) a partir da tabela por leitura.

    Medidas de QUALIDADE (gráficos aprovado × reprovado -- "tudo na base"):
      chuva, nivel_range, nivel_final -> (aprovadas, todas as leituras avaliadas).
    Medidas do CÁLCULO DE DESEMPENHO (nota -- decisão de 27/09, "dados consistidos"):
      chuva_cd, nivel_cd -> (consistidas, coletadas), onde
        coletada   = leitura que chegou COM VALOR (leitura em branco não é dado coletado;
                     a falta de dado já é medida no 2.2);
        consistida = leitura coletada que recebeu um RESULTADO FINAL da consistência,
                     aprovado ou reprovado (no nível: reprovada/suspeita no Range, ou
                     aprovada/reprovada no Persist). Ficam como NÃO consistidas as
                     leituras com valor que não foram testadas (ex.: "Teste não
                     realizado" por lacuna na janela do Persist; Persist sem cálculo)."""
    m = {}
    if "status_chuva" in tabela:
        ch = tabela["status_chuva"].dropna()
        m["chuva"] = (int((ch == "aprovado").sum()), len(ch))
        col = tabela.loc[tabela["status_chuva"].notna() & tabela["dado_bruto_chuva"].notna()]
        m["chuva_cd"] = (int(col["status_chuva"].isin(RESULTADO_FINAL_CHUVA).sum()), len(col))
    if "status_nivel_range" in tabela:
        rg = tabela["status_nivel_range"].dropna()
        m["nivel_range"] = (int((rg == "aprovado").sum()), len(rg))
        base_final = tabela.loc[tabela["status_nivel_range"].notna(), "status_nivel_persist"]
        m["nivel_final"] = (int((base_final == "aprovado").sum()), len(base_final))
        col = tabela.loc[tabela["status_nivel_range"].notna() & tabela["dado_bruto_nivel"].notna()]
        consistida = (col["status_nivel_range"].isin(RESULTADO_FINAL_RANGE_SEM_PERSIST)
                      | ((col["status_nivel_range"] == "aprovado")
                         & col["status_nivel_persist"].isin(RESULTADO_FINAL_PERSIST)))
        m["nivel_cd"] = (int(consistida.sum()), len(col))
    return m


def _contar_chirps(tabela):
    """RESERVA/DORMANT desde 28/09/2026 -- ver _contar_merge (usada na
    chamada real). Mantida sem alteração."""
    if "divergencia_chuva" not in tabela:
        return 0, 0
    c = tabela.dropna(subset=["divergencia_chuva"]).copy()
    if c.empty:
        return 0, 0
    c["dia"] = pd.to_datetime(c["data"]).dt.normalize()
    c = c.drop_duplicates(["codigo_estacao", "dia"])
    div = int(c["divergencia_chuva"].astype(float).sum())
    return len(c) - div, div


def _contar_merge(tabela):
    if "divergencia_merge" not in tabela:
        return 0, 0
    c = tabela.dropna(subset=["divergencia_merge"]).copy()
    if c.empty:
        return 0, 0
    c["dia"] = pd.to_datetime(c["data"]).dt.normalize()
    c = c.drop_duplicates(["codigo_estacao", "dia"])
    div = int(c["divergencia_merge"].astype(float).sum())
    return len(c) - div, div


ROTULOS = {
    "chuva": "Chuva — valores impossíveis (acumulado mensal)",
    "nivel_range": "Nível — Range (alcance)",
    "nivel_final": "Nível — resultado final (Range + Persist)",
    "chuva_cd": "Chuva — dados consistidos (nota)",
    "nivel_cd": "Nível — dados consistidos (nota)",
}


def resumir(tabela_final, data_execucao, data_fim, sem_dado, merge_ok):
    """Devolve (df_resumo, df_por_estacao)."""
    linhas = []
    for chave, (aprov, base) in _medidas(tabela_final).items():
        pct = round(aprov / base * 100, 2) if base else None
        col = "status_chuva" if chave.startswith("chuva") else "status_nivel_range"
        n_est = int(tabela_final.loc[tabela_final[col].notna(), "codigo_estacao"].nunique())
        # A NOTA (CD) vem só das medidas de dados consistidos (chuva_cd, nivel_cd).
        # Nas linhas *_cd: aprovados = consistidas, avaliados = coletadas,
        # reprovados = coletadas não consistidas.
        linhas.append({
            "medida": chave, "rotulo": ROTULOS[chave], "aprovados": aprov, "avaliados": base,
            "reprovados": base - aprov, "percentual": pct,
            "nota": nota_2_8(pct) if chave in ("chuva_cd", "nivel_cd") else None,
            "n_estacoes": n_est,
        })
    conv, div = _contar_merge(tabela_final)
    # O MERGE é publicado sem atraso (0 dias, medido em 28/09/2026), mas o
    # período efetivamente comparado ainda termina no último dia com valor
    # do satélite, por segurança (ex.: rodada em que o MERGE falhou nos
    # últimos dias).
    fim_merge = None
    if "divergencia_merge" in tabela_final and tabela_final["divergencia_merge"].notna().any():
        fim_merge = str(pd.to_datetime(tabela_final.loc[tabela_final["divergencia_merge"].notna(), "data"]).max().date())
    linhas.append({"medida": "merge", "rotulo": "Chuva × MERGE (estação-dia)", "aprovados": conv,
                   "avaliados": conv + div, "reprovados": div,
                   "percentual": round(conv / (conv + div) * 100, 2) if conv + div else None,
                   "nota": None, "n_estacoes": None})
    resumo = pd.DataFrame(linhas)
    resumo.insert(0, "data_execucao", data_execucao)
    resumo["periodo_inicio"] = config_cg.DATA_INICIO_CG_HIDRO
    resumo["periodo_fim"] = str(data_fim)
    if fim_merge:
        resumo.loc[resumo["medida"] == "merge", "periodo_fim"] = fim_merge
    resumo["merge_status"] = "ok" if merge_ok else "indisponível"
    resumo["estacoes_sem_dado"] = " | ".join(sorted(sem_dado))

    por_estacao = []
    for codigo, grupo in tabela_final.groupby("codigo_estacao"):
        for chave, (aprov, base) in _medidas(grupo).items():
            if base == 0:
                continue
            por_estacao.append({"codigo_estacao": codigo, "medida": chave, "aprovados": aprov,
                                "avaliados": base, "percentual": round(aprov / base * 100, 2)})
    return resumo, pd.DataFrame(por_estacao)


def resumo_longo_para_looker(tabela_final, data_execucao):
    """Mesmo formato do antigo fato_consistencia.csv (data_execucao,
    codigo_estacao, teste, flag, percentual) -- agora com os testes do 2.8,
    para a planilha do Looker continuar atualizando."""
    linhas = []
    for coluna in ["status_chuva", "status_nivel_range", "status_nivel_persist"]:
        if coluna not in tabela_final:
            continue
        for codigo, serie in tabela_final.groupby("codigo_estacao")[coluna]:
            serie = serie.dropna()
            if serie.empty:
                continue
            for flag, pct in serie.value_counts(normalize=True).mul(100).round(2).items():
                linhas.append({"data_execucao": data_execucao, "codigo_estacao": codigo,
                               "teste": coluna, "flag": flag, "percentual": pct})
    return pd.DataFrame(linhas)


def montar_tabela_final(tabela_chuva, tabelas_nivel):
    tabela_nivel = pd.concat(tabelas_nivel, ignore_index=True) if tabelas_nivel else pd.DataFrame(
        columns=["codigo_estacao", "data", "dado_bruto_nivel", "status_nivel_range", "status_nivel_persist"])
    if tabela_chuva.empty:
        tabela_chuva = pd.DataFrame(columns=["codigo_estacao", "data"])
    return pd.merge(tabela_chuva, tabela_nivel, on=["codigo_estacao", "data"], how="outer")
