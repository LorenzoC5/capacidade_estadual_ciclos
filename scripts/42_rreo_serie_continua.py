"""Monta a série contínua do RREO por estado: PDFs (até 2014) + API do Siconfi (2015 em diante).

Entradas:
  dados/02_intermediario/rreo_pdf_extraido.csv            (41_rreo_extrair.py)
  dados/01_bruto/siconfi/rreo/RREO-Anexo_01/...            (01_siconfi.py rreo)
Saídas:
  dados/02_intermediario/rreo_serie_continua_bimestral.csv  acumulado e fluxo por bimestre
  dados/03_final/rreo_serie_continua_anual.csv               6º bimestre de cada ano
  dados/02_intermediario/rreo_validacao.csv                  checagens de qualidade

Regras:
  - de 2015 em diante, vale a API; antes, o PDF;
  - se houver PDF de 2015 (recomendado), ele é comparado com a API para medir o
    erro da extração; diferença acima de 1% em alguma variável gera alerta;
  - o acumulado precisa crescer ao longo do ano; quebras são marcadas;
  - a coluna "fonte" diz de onde veio cada número, e "metodo" como foi escolhido.

Uso:
    python scripts/42_rreo_serie_continua.py
"""
from __future__ import annotations

import importlib

import pandas as pd

from _util import RAIZ, log

INTER = RAIZ / "dados" / "02_intermediario"
FINAL = RAIZ / "dados" / "03_final"
ANO_API = 2015


def api() -> pd.DataFrame:
    p1 = importlib.import_module("20_passo1_ajuste_crises")
    df = p1.painel_bimestral()
    if df.empty:
        log.warning("Sem RREO da API em disco; rodar 01_siconfi.py rreo")
        return pd.DataFrame(columns=["uf", "ano", "bimestre", "variavel", "acumulado"])
    df = df.rename(columns={"periodo": "bimestre", "categoria": "variavel"})
    df["fonte"], df["metodo"] = "api_siconfi", "api"
    return df[["uf", "ano", "bimestre", "variavel", "acumulado", "fonte", "metodo"]]


def pdfs() -> pd.DataFrame:
    arq = INTER / "rreo_pdf_extraido.csv"
    if not arq.exists():
        log.warning("Sem %s; rodar 40 e 41 antes", arq.name)
        return pd.DataFrame(columns=["uf", "ano", "bimestre", "variavel", "acumulado"])
    df = pd.read_csv(arq).rename(columns={"valor": "acumulado"})
    df["fonte"] = "pdf_portal_estadual"
    return df[["uf", "ano", "bimestre", "variavel", "acumulado", "fonte", "metodo"]]


def validar(pdf: pd.DataFrame, ap: pd.DataFrame, serie: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    sob = pdf.merge(ap, on=["uf", "ano", "bimestre", "variavel"], suffixes=("_pdf", "_api"))
    for _, r in sob.iterrows():
        dif = (r.acumulado_pdf - r.acumulado_api) / r.acumulado_api if r.acumulado_api else None
        linhas.append({"tipo": "pdf_vs_api", "uf": r.uf, "ano": r.ano, "bimestre": r.bimestre,
                       "variavel": r.variavel, "valor": dif, "alerta": dif is not None and abs(dif) > 0.01})
    s = serie.sort_values(["uf", "variavel", "ano", "bimestre"])
    s["queda"] = s.groupby(["uf", "variavel", "ano"])["acumulado"].diff() < 0
    for _, r in s[s.queda].iterrows():
        linhas.append({"tipo": "acumulado_cai", "uf": r.uf, "ano": r.ano, "bimestre": r.bimestre,
                       "variavel": r.variavel, "valor": None, "alerta": True})
    falta = s.groupby(["uf", "ano"])["bimestre"].nunique().loc[lambda x: x < 6]
    for (uf, ano), n in falta.items():
        linhas.append({"tipo": "bimestres_faltando", "uf": uf, "ano": ano, "bimestre": None,
                       "variavel": None, "valor": 6 - n, "alerta": True})
    return pd.DataFrame(linhas)


if __name__ == "__main__":
    ap, pdf = api(), pdfs()
    serie = pd.concat([pdf[pdf.ano < ANO_API], ap[ap.ano >= ANO_API]], ignore_index=True)
    serie = serie.dropna(subset=["acumulado"]).sort_values(["uf", "variavel", "ano", "bimestre"])
    serie["fluxo"] = serie.groupby(["uf", "variavel", "ano"])["acumulado"].diff().fillna(serie["acumulado"])
    INTER.mkdir(parents=True, exist_ok=True)
    FINAL.mkdir(parents=True, exist_ok=True)
    serie.to_csv(INTER / "rreo_serie_continua_bimestral.csv", index=False)
    anual = serie[serie.bimestre == 6].drop(columns=["bimestre", "fluxo"]).rename(columns={"acumulado": "valor_anual"})
    anual.to_csv(FINAL / "rreo_serie_continua_anual.csv", index=False)
    val = validar(pdf, ap, serie)
    val.to_csv(INTER / "rreo_validacao.csv", index=False)
    cobertura = anual.groupby("uf")["ano"].agg(["min", "max", "nunique"])
    log.info("Série contínua: %s UFs; cobertura por UF:\n%s", anual.uf.nunique(), cobertura.to_string())
    if len(val):
        log.info("Alertas de validação: %s", val[val.alerta].groupby("tipo").size().to_dict())
