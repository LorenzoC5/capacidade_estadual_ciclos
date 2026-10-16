"""Séries históricas estaduais do Ipeadata (base Regional).

O SICONFI cobre os estados a partir de 2013/2015. Para olhar a crise de 2008-09 e
o período anterior à LRF, o Ipeadata reúne séries anuais de receitas, despesas e
dívida dos estados (fonte STN e outras), algumas desde os anos 1980.

O script lista os metadados de todas as séries, filtra as da base Regional ligadas
a finanças públicas, grava o catálogo e baixa apenas os valores no nível "Estados".

Uso:
    python scripts/05_ipeadata.py
"""
from __future__ import annotations

import re

import pandas as pd

from _util import BRUTO, get, ja_existe, log, salvar

API = "http://www.ipeadata.gov.br/api/odata4"
FILTRO_NOME = re.compile(
    r"receita|despesa|d[ií]vida|icms|transfer[eê]ncia|fpe|investimento|pessoal|"
    r"juros|amortiza|super[aá]vit|d[eé]ficit|resultado|arrecada", re.I)


def catalogo() -> pd.DataFrame:
    meta = get(f"{API}/Metadados", timeout=300)
    if not meta:
        return pd.DataFrame()
    df = pd.DataFrame(meta.get("value", []))
    regional = df[df["BASNOME"].str.contains("Regional", case=False, na=False)]
    fiscal = regional[regional["SERNOME"].str.contains(FILTRO_NOME, na=False)]
    colunas = [c for c in ["SERCODIGO", "SERNOME", "FNTSIGLA", "FNTNOME", "PERNOME",
                           "UNINOME", "SERMULTIPLICADOR", "SERSTATUS", "SERCOMENTARIO"] if c in df.columns]
    fiscal = fiscal[colunas]
    salvar(fiscal, BRUTO / "ipeadata" / "_catalogo_regional_fiscal.csv")
    log.info("Ipeadata: %s séries regionais de finanças públicas", len(fiscal))
    return fiscal


def baixar(codigo: str, nome: str):
    destino = BRUTO / "ipeadata" / f"{codigo}.csv"
    if ja_existe(destino):
        return
    corpo = get(f"{API}/ValoresSerie(SERCODIGO='{codigo}')", timeout=300)
    if not corpo:
        return
    df = pd.DataFrame(corpo.get("value", []))
    if "NIVNOME" in df.columns:
        df = df[df["NIVNOME"].str.lower() == "estados"]
    if not df.empty:
        df.insert(0, "SERNOME", nome)
        salvar(df, destino)
        log.info("Ipeadata %s: %s obs.", codigo, len(df))


if __name__ == "__main__":
    for _, r in catalogo().iterrows():
        baixar(r["SERCODIGO"], r["SERNOME"])
