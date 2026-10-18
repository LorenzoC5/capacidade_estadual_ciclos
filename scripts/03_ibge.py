"""Dados macroeconômicos estaduais do IBGE via API SIDRA.

Define o ciclo econômico de cada UF (PIB anual, atividade mensal, desemprego)
e os denominadores (população, PIB nominal).

Estratégia:
  a) Descobre e baixa todas as tabelas da pesquisa "Contas Regionais" que têm
     recorte por UF (PIB, VAB por atividade, variação em volume, deflator).
  b) Baixa uma lista fixa de tabelas conjunturais. Antes de baixar, grava o
     metadado de cada tabela em ibge/_metadados para conferência do conteúdo.

Uso:
    python scripts/03_ibge.py
"""
from __future__ import annotations

import json

import pandas as pd

from _util import BRUTO, get, ja_existe, log, salvar

SIDRA = "https://apisidra.ibge.gov.br/values"
AGREG = "https://servicodados.ibge.gov.br/api/v3/agregados"

# Tabelas conjunturais por UF. Conferir o metadado gravado antes de usar.
TABELAS_FIXAS = {
    5938: "Contas Regionais: PIB a preços correntes, impostos e VAB por UF (anual, 2002+)",
    6579: "População residente estimada por UF (anual)",
    4099: "PNAD Contínua: taxas de desocupação e subutilização por UF (trimestral)",
    8888: "PIM-PF Regional: produção física industrial por UF (mensal)",
    8880: "PMC: volume e receita do varejo por UF (mensal)",
    5906: "PMS: volume e receita de serviços por UF (mensal)",
}
TAMANHO_LOTE = 48  # períodos por requisição, para ficar abaixo do limite de 100 mil valores


def metadados(tabela: int) -> dict | None:
    meta = get(f"{AGREG}/{tabela}/metadados")
    if meta:
        destino = BRUTO / "ibge" / "_metadados" / f"t{tabela}.json"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def baixar_tabela(tabela: int, rotulo: str):
    destino = BRUTO / "ibge" / f"sidra_t{tabela}.csv"
    if ja_existe(destino):
        return
    meta = metadados(tabela)
    if not meta:
        log.warning("Tabela %s sem metadado; pulando", tabela)
        return
    niveis = meta.get("nivelTerritorial", {}).get("Administrativo", [])
    if "N3" not in niveis:
        log.info("Tabela %s não tem recorte por UF (N3); pulando", tabela)
        return
    periodos = [p["id"] for p in (get(f"{AGREG}/{tabela}/periodos") or [])]
    partes = []
    for i in range(0, max(len(periodos), 1), TAMANHO_LOTE):
        lote = ",".join(periodos[i:i + TAMANHO_LOTE]) if periodos else "all"
        dados = get(f"{SIDRA}/t/{tabela}/n3/all/v/all/p/{lote}")
        if dados and len(dados) > 1:
            cab = dados[0]
            partes.append(pd.DataFrame(dados[1:]).rename(columns=cab))
    if partes:
        df = pd.concat(partes, ignore_index=True)
        n = salvar(df, destino)
        log.info("SIDRA %s (%s): %s linhas | %s", tabela, meta.get("nome", "")[:60], n, rotulo)


def tabelas_contas_regionais() -> dict[int, str]:
    lista = get(AGREG) or []
    achadas = {}
    for pesquisa in lista:
        if "contas regionais" in pesquisa.get("nome", "").lower():
            for ag in pesquisa.get("agregados", []):
                achadas[int(ag["id"])] = ag["nome"]
    cat = pd.DataFrame([{"tabela": k, "nome": v} for k, v in achadas.items()])
    salvar(cat, BRUTO / "ibge" / "_catalogo_contas_regionais.csv")
    log.info("Contas Regionais: %s tabelas encontradas", len(achadas))
    return achadas


if __name__ == "__main__":
    alvos = dict(TABELAS_FIXAS)
    for t, nome in tabelas_contas_regionais().items():
        alvos.setdefault(t, f"Contas Regionais: {nome}")
    for t, rotulo in alvos.items():
        baixar_tabela(t, rotulo)
