"""Séries do Banco Central (SGS).

a) Séries nacionais fixas: preços, juros, atividade e PIB mensal.
b) Descoberta pelo portal de dados abertos do BCB (CKAN) das séries:
   - IBCR (atividade econômica regional por estado e região, mensal, 2003+);
   - estatísticas fiscais de governos estaduais (dívida líquida, NFSP);
   - arrecadação de ICMS por UF, quando houver.
   O catálogo descoberto vai para bcb/_catalogo_sgs.csv; revisar e podar se vier ruído.

Uso:
    python scripts/04_bcb.py
"""
from __future__ import annotations

import datetime as dt
import re

import pandas as pd

from _util import BRUTO, get, ja_existe, log, salvar

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados"
CKAN = "https://dadosabertos.bcb.gov.br/api/3/action/package_search"

SERIES_FIXAS = {
    433: "IPCA - variação mensal (%)",
    13522: "IPCA - acumulado 12 meses (%)",
    189: "IGP-M - variação mensal (%)",
    432: "Meta Selic (% a.a.)",
    4189: "Selic acumulada no mês anualizada (% a.a.)",
    4380: "PIB mensal - valores correntes (R$ milhões)",
    24363: "IBC-Br - sem ajuste sazonal",
    24364: "IBC-Br - com ajuste sazonal",
    25381: "IBCR Centro-Oeste - sem ajuste sazonal",
    25382: "IBCR Centro-Oeste - com ajuste sazonal",
}

DESCOBERTA = [
    ("Índice de Atividade Econômica Regional", r"atividade econ[oô]mica regional|ibcr"),
    ("governos estaduais dívida líquida", r"governos? estaduais|estados e munic"),
    ("necessidades de financiamento governos estaduais", r"governos? estaduais"),
    ("ICMS arrecadação", r"\bicms\b"),
]


def baixar_serie(codigo: int, rotulo: str, inicio: int = 1995):
    destino = BRUTO / "bcb" / f"sgs_{codigo}.csv"
    if ja_existe(destino):
        return
    partes, hoje = [], dt.date.today()
    for ano in range(inicio, hoje.year + 1, 10):  # janelas de 10 anos (limite da API)
        ini, fim = f"01/01/{ano}", f"31/12/{min(ano + 9, hoje.year)}"
        dados = get(SGS.format(codigo=codigo), {"formato": "json", "dataInicial": ini, "dataFinal": fim})
        if dados:
            partes.extend(dados)
    if partes:
        df = pd.DataFrame(partes).drop_duplicates()
        df.insert(0, "codigo_sgs", codigo)
        df.insert(1, "serie", rotulo)
        n = salvar(df, destino)
        log.info("SGS %s (%s): %s obs.", codigo, rotulo, n)


def descobrir() -> dict[int, str]:
    achadas = {}
    for consulta, filtro in DESCOBERTA:
        inicio = 0
        while True:
            corpo = get(CKAN, {"q": consulta, "rows": 500, "start": inicio})
            if not corpo or not corpo.get("success"):
                break
            res = corpo["result"]["results"]
            for pkg in res:
                m = re.match(r"^(\d+)-sgs$", pkg.get("name", ""))
                if m and re.search(filtro, pkg.get("title", ""), flags=re.I):
                    achadas[int(m.group(1))] = pkg["title"]
            inicio += len(res)
            if not res or inicio >= corpo["result"]["count"]:
                break
    cat = pd.DataFrame([{"codigo_sgs": k, "titulo": v} for k, v in sorted(achadas.items())])
    salvar(cat, BRUTO / "bcb" / "_catalogo_sgs.csv")
    log.info("Descoberta BCB: %s séries", len(achadas))
    return achadas


if __name__ == "__main__":
    alvos = dict(SERIES_FIXAS)
    for cod, titulo in descobrir().items():
        alvos.setdefault(cod, titulo)
    for cod, rotulo in alvos.items():
        baixar_serie(cod, rotulo)
