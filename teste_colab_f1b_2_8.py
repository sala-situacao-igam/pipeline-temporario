"""
Descrição: TESTE no Colab da etapa 1 da Fase 1b -- o novo
pipeline_consistencia.py (disponibilidade do 2.2 + indicador 2.8).
Roda tudo com os dados REAIS do Drive, mas NÃO GRAVA NADA no Drive
(salvar_no_drive=False): as saídas ficam na pasta local "saida_teste_2_8/".

Como usar no Colab:
1. Faça upload, na raiz da sessão, de:
   - chave_servico.json
   - todos os .py atuais do repositório pipeline-hidroweb-igam
   - os .py de scripts_dash_cg (eles SUBSTITUEM o pipeline_consistencia.py
     do repositório -- suba depois dos do repositório)
   - (opcional) indicador_2_8_bruto.csv da sua rodada anterior, para
     conferência leitura a leitura
2. Para ter o CHIRPS no teste: numa célula antes, rode
       import ee; ee.Authenticate()
   (sem isso o teste roda igual, só sem a comparação com o CHIRPS)
3. %run teste_colab_f1b_2_8.py

O que conferir:
- RESUMO do 2.8: chuva e nível (resultado final) com percentual e nota.
- Se o indicador_2_8_bruto.csv estiver na pasta: "divergentes 0" nos três
  status para o período em comum (a janela do Persist é a de config_cg).
- Contagem de estações: chuva e nível (nível sem as só pluviométricas).
"""
import os

import pandas as pd

import pipeline_consistencia

CAMINHO_CHAVE = os.environ.get("CAMINHO_CHAVE_JSON", "chave_servico.json")
PASTA_SAIDA = "saida_teste_2_8"
CAMINHO_BRUTO_ANTERIOR = "indicador_2_8_bruto.csv"


def conferir_com_rodada_anterior(tabela):
    if not os.path.exists(CAMINHO_BRUTO_ANTERIOR):
        print(f"\n({CAMINHO_BRUTO_ANTERIOR} não está na pasta -- conferência leitura a leitura pulada.)")
        return
    anterior = pd.read_csv(CAMINHO_BRUTO_ANTERIOR, sep=None, engine="python", dtype={"codigo_estacao": str})
    anterior["codigo_estacao"] = anterior["codigo_estacao"].str.zfill(8)
    anterior["data"] = pd.to_datetime(anterior["data"])
    atual = tabela.copy()
    atual["data"] = pd.to_datetime(atual["data"])
    m = atual.merge(anterior, on=["codigo_estacao", "data"], suffixes=("_novo", "_anterior"))
    print("\nConferência com a rodada anterior (só leituras em comum):")
    for coluna in ["status_chuva", "status_nivel_range", "status_nivel_persist"]:
        ok = m[f"{coluna}_novo"].notna() & m[f"{coluna}_anterior"].notna()
        dif = (m.loc[ok, f"{coluna}_novo"] != m.loc[ok, f"{coluna}_anterior"]).sum()
        print(f"  {coluna}: {ok.sum()} leituras comparadas, {dif} divergentes")


def main():
    os.makedirs(PASTA_SAIDA, exist_ok=True)
    r = pipeline_consistencia.rodar_para_todas_estacoes(CAMINHO_CHAVE, salvar_no_drive=False)
    if r is None:
        return

    r["resumo_2_8"].to_csv(os.path.join(PASTA_SAIDA, "indicador_2_8_resumo.csv"), index=False)
    r["por_estacao_2_8"].to_csv(os.path.join(PASTA_SAIDA, "indicador_2_8_por_estacao.csv"), index=False)
    r["tabela_2_8"].to_csv(os.path.join(PASTA_SAIDA, "indicador_2_8_leituras.csv"), index=False)

    print("\n" + "=" * 60 + "\nRESUMO DO 2.8 (soma da rede)\n" + "=" * 60)
    colunas = ["rotulo", "aprovados", "avaliados", "percentual", "nota", "n_estacoes"]
    print(r["resumo_2_8"][colunas].to_string(index=False))
    #print(f"CHIRPS: {r['resumo_2_8']['chirps_status'].iloc[0]}")
    print(f"Estações sem leitura no período: {r['resumo_2_8']['estacoes_sem_dado'].iloc[0] or '(nenhuma)'}")

    conferir_com_rodada_anterior(r["tabela_2_8"])
    print(f"\nArquivos em {PASTA_SAIDA}/ (nada foi gravado no Drive).")


if __name__ == "__main__":
    main()
