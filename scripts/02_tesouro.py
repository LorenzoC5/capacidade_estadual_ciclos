"""Demais bases do Tesouro Nacional.

1. Transferências constitucionais aos estados (FPE, IPI-Exp., CIDE, LC 87/Kandir, auxílios
   da LC 173/2020 e compensações da LC 194/2022 quando registradas como transferência).
2. SADIPEM: pedidos de verificação de limites (PVL) de operações de crédito dos estados.
3. Tesouro Transparente (CKAN): CAPAG dos estados, Boletim de Finanças dos Entes
   Subnacionais, garantias honradas pela União, haveres e dívida dos estados com a União,
   Regime de Recuperação Fiscal, PAF, Execução Orçamentária dos Estados (1995-2013) e
   FINBRA histórico (1989-2012, em banco Access). O script busca por palavra-chave, grava o catálogo
   encontrado e baixa os arquivos dos conjuntos cujo título bate com os filtros.

Uso:
    python scripts/02_tesouro.py transferencias --anos 1997 2026
    python scripts/02_tesouro.py sadipem
    python scripts/02_tesouro.py ckan
    python scripts/02_tesouro.py tudo
"""
from __future__ import annotations

import argparse
import datetime as dt
import re

import pandas as pd

from _util import BRUTO, SADIPEM, TRANSF, get, ja_existe, log, ords_todos, salvar

CKAN = "https://www.tesourotransparente.gov.br/ckan/api/3/action"

# (consulta, regex aplicada ao título para filtrar ruído)
CKAN_CONSULTAS = [
    ("capacidade de pagamento estados", r"capacidade de pagamento.*estado|capag.*estado"),
    ("boletim de finanças dos entes subnacionais", r"boletim de finan"),
    ("garantias honradas", r"garantias honradas|honra"),
    ("haveres estados", r"haveres|d[ií]vida.*estados|refinanciamento"),
    ("programa de reestruturação e ajuste fiscal", r"ajuste fiscal|paf\b|acompanhamento.*fiscal"),
    ("regime de recuperação fiscal", r"recupera[cç][aã]o fiscal"),
    ("operações de crédito estados", r"opera[cç][oõ]es de cr[eé]dito"),
    ("transferências estados", r"transfer[eê]ncias.*estado|transfer[eê]ncias constitucionais"),
    ("execução orçamentária dos estados", r"execu[cç][aã]o or[cç]ament[aá]ria.*estado"),
    ("finbra dados contábeis", r"finbra|dados cont[aá]beis"),
    ("RREO estados", r"\brreo\b|execu[cç][aã]o or[cç]ament[aá]ria"),
    ("RGF estados", r"\brgf\b|gest[aã]o fiscal"),
]


def transferencias(ano_ini: int, ano_fim: int):
    pasta = BRUTO / "transferencias"
    for nome in ("estados", "transferencias"):
        corpo = get(f"{TRANSF}/{nome}")
        if corpo:
            itens = corpo if isinstance(corpo, list) else corpo.get("items") or corpo.get("registros")
            salvar(itens, pasta / f"dicionario_{nome}.csv")
    for ano in range(ano_ini, ano_fim + 1):
        destino = pasta / f"transferencias_por_estado_{ano}.csv"
        if ja_existe(destino):
            continue
        corpo = get(f"{TRANSF}/por_estados", {"p_ano": ano, "p_sn_detalhar": "S"})
        itens = corpo if isinstance(corpo, list) else (corpo or {}).get("items") or (corpo or {}).get("registros")
        n = salvar(itens or [], destino)
        log.info("Transferências %s: %s linhas", ano, n)


def sadipem():
    itens = ords_todos(SADIPEM, "/pvl", {"tipo_interessado": "Estado"})
    n = salvar(itens, BRUTO / "sadipem" / "pvl_estados.csv")
    log.info("SADIPEM PVL estados: %s linhas", n)
    if n == 0:
        log.warning("Nenhum PVL com tipo_interessado='Estado'. Rodar sem filtro e filtrar depois.")
        itens = ords_todos(SADIPEM, "/pvl", {})
        salvar(itens, BRUTO / "sadipem" / "pvl_todos.csv")


def _slug(txt: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", txt.lower()).strip("_")[:80]


def ckan():
    pasta = BRUTO / "tesouro_transparente"
    catalogo = []
    for consulta, filtro in CKAN_CONSULTAS:
        corpo = get(f"{CKAN}/package_search", {"q": consulta, "rows": 100})
        if not corpo or not corpo.get("success"):
            log.warning("CKAN sem resposta para '%s'", consulta)
            continue
        for pkg in corpo["result"]["results"]:
            titulo = pkg.get("title", "")
            if not re.search(filtro, titulo, flags=re.I):
                continue
            for res in pkg.get("resources", []):
                catalogo.append({
                    "consulta": consulta, "dataset_id": pkg["id"], "dataset": titulo,
                    "recurso": res.get("name"), "formato": res.get("format"),
                    "url": res.get("url"), "atualizado": res.get("last_modified"),
                })
    cat = pd.DataFrame(catalogo).drop_duplicates(subset=["url"])
    salvar(cat, pasta / "_catalogo_ckan.csv")
    log.info("Catálogo CKAN: %s recursos em %s conjuntos", len(cat), cat["dataset"].nunique() if len(cat) else 0)

    for _, r in cat.iterrows():
        if not r.url or str(r.formato).upper() in ("HTML", "API", ""):
            continue
        nome = r.url.split("?")[0].rstrip("/").split("/")[-1] or f"{_slug(r.recurso)}.bin"
        destino = pasta / _slug(r.dataset) / nome
        if ja_existe(destino):
            continue
        conteudo = get(r.url, como_json=False, timeout=300)
        if conteudo:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(conteudo)
            log.info("Baixado: %s", destino.relative_to(BRUTO))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("alvo", choices=["transferencias", "sadipem", "ckan", "tudo"])
    ap.add_argument("--anos", nargs=2, type=int, default=(1997, dt.date.today().year))
    a = ap.parse_args()
    if a.alvo in ("transferencias", "tudo"):
        transferencias(*a.anos)
    if a.alvo in ("sadipem", "tudo"):
        sadipem()
    if a.alvo in ("ckan", "tudo"):
        ckan()
