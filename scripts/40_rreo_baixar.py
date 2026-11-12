"""Baixa os RREOs anteriores a 2015 (e 2015, para validação) dos portais estaduais.

A API do Siconfi só tem o RREO dos estados a partir de 2015. Antes disso, os
relatórios estão nos portais de cada estado, em PDF (às vezes em XLS). Esta
rotina percorre a página indicada em dados/00_referencia/rreo_portais.csv,
segue links até a profundidade escolhida e baixa os arquivos que parecem ser
RREO, identificando ano e bimestre pelo texto do link ou pelo endereço.

Cada portal é diferente. O fluxo esperado é rodar por estado, olhar o manifesto
gerado e, se preciso, ajustar a URL de partida, a profundidade ou os filtros
daquele estado no catálogo.

Uso:
    python scripts/40_rreo_baixar.py --uf MT --anos 2000 2015
    python scripts/40_rreo_baixar.py --uf MT --profundidade 3 --listar   # só lista, não baixa
    python scripts/40_rreo_baixar.py --todos

Saídas:
    dados/01_bruto/rreo_rgf_portais/<UF>/<ano>/<UF>_<ano>_b<N>.<ext>
    dados/01_bruto/rreo_rgf_portais/<UF>/_manifesto.csv   (todos os links avaliados)
"""
from __future__ import annotations

import argparse
import hashlib
import re
import time
import unicodedata
from urllib.parse import urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup

from _util import BRUTO, REF, log

DESTINO = BRUTO / "rreo_rgf_portais"
HEADERS = {"User-Agent": "Mozilla/5.0 (pesquisa academica FEA-USP; contato via SEFAZ-MT)"}
EXT_ARQ = (".pdf", ".xls", ".xlsx", ".zip")
RX_RREO = re.compile(r"RREO|RESUMIDO DA EXECU|EXECUCAO ORCAMENTARIA|LRF|RESPONSABILIDADE FISCAL", re.I)
RX_EXCLUI = re.compile(r"\bRGF\b|GESTAO FISCAL|MUNICIP|PREFEITURA|SIMPLIFICADO", re.I)
RX_ANO = re.compile(r"(?<!\d)(20[0-2]\d)(?!\d)")
RX_BIM = re.compile(r"(?<!\d)([1-6])\s*(?:º|o|°|ª)?\s*(?:BIM|BIMESTRE)", re.I)
MESES_FIM = {"FEV": 1, "ABR": 2, "JUN": 3, "AGO": 4, "OUT": 5, "DEZ": 6}


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def identificar(texto: str) -> tuple[int | None, int | None]:
    """Ano e bimestre a partir do texto do link e do endereço."""
    t = norm(texto)
    anos = RX_ANO.findall(t)
    ano = int(anos[-1]) if anos else None
    m = RX_BIM.search(t)
    bim = int(m.group(1)) if m else None
    if bim is None:  # “JANEIRO A DEZEMBRO”, “NOV-DEZ” etc.
        for mes, b in MESES_FIM.items():
            if re.search(rf"\b{mes}", t) and re.search(r"\bA\b|-|/", t):
                bim = b
    return ano, bim


def links_da_pagina(url: str) -> list[tuple[str, str]]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        log.warning("Falha ao abrir %s: %s", url, e)
        return []
    sopa = BeautifulSoup(r.text, "html.parser")
    saida = []
    for a in sopa.find_all("a", href=True):
        href = urljoin(url, a["href"])
        texto = " ".join([a.get_text(" "), a.get("title", ""), href])
        saida.append((href, texto))
    return saida


def percorrer(inicio: str, profundidade: int) -> list[dict]:
    dominio = urlparse(inicio).netloc
    visitadas, fila, achados = set(), [(inicio, 0, "")], []
    while fila:
        url, nivel, contexto = fila.pop(0)
        if url in visitadas or nivel > profundidade:
            continue
        visitadas.add(url)
        for href, texto in links_da_pagina(url):
            texto_total = f"{contexto} {texto}"
            eh_arquivo = href.lower().split("?")[0].endswith(EXT_ARQ) or "/documents/" in href
            if eh_arquivo:
                achados.append({"url": href, "texto": norm(texto_total)[:300], "pagina": url})
            elif urlparse(href).netloc == dominio and RX_RREO.search(norm(texto)) and nivel < profundidade:
                fila.append((href, nivel + 1, norm(texto)[:120]))
        time.sleep(0.5)
    return achados


def ckan(url_dataset: str) -> list[dict]:
    base = url_dataset.split("/dataset/")[0]
    nome = url_dataset.rstrip("/").split("/")[-1]
    r = requests.get(f"{base}/api/3/action/package_show", params={"id": nome}, headers=HEADERS, timeout=60)
    r.raise_for_status()
    return [{"url": res["url"], "texto": norm(f"{res.get('name', '')} {res['url']}"), "pagina": url_dataset}
            for res in r.json()["result"]["resources"]]


def baixar(uf: str, tipo: str, url: str, anos: tuple[int, int], profundidade: int, listar: bool):
    achados = ckan(url) if tipo == "ckan" else percorrer(url, profundidade)
    man = pd.DataFrame(achados).drop_duplicates("url") if achados else pd.DataFrame(columns=["url", "texto", "pagina"])
    if man.empty:
        log.warning("%s: nenhum arquivo encontrado a partir de %s", uf, url)
        return
    man[["ano", "bimestre"]] = man["texto"].apply(lambda t: pd.Series(identificar(t)))
    man["parece_rreo"] = man["texto"].str.contains(RX_RREO) & ~man["texto"].str.contains(RX_EXCLUI)
    man["no_periodo"] = man["ano"].between(*anos)
    man["status"] = ""
    pasta = DESTINO / uf
    pasta.mkdir(parents=True, exist_ok=True)
    for i, linha in man.iterrows():
        if listar or not (linha.parece_rreo and linha.no_periodo and pd.notna(linha.bimestre)):
            continue
        ext = next((e for e in EXT_ARQ if linha.url.lower().split("?")[0].endswith(e)), ".pdf")
        arq = pasta / f"{int(linha.ano)}" / f"{uf}_{int(linha.ano)}_b{int(linha.bimestre)}{ext}"
        if arq.exists():
            man.at[i, "status"] = "ja_existia"
            continue
        try:
            r = requests.get(linha.url, headers=HEADERS, timeout=120)
            r.raise_for_status()
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_bytes(r.content)
            man.at[i, "status"] = "baixado"
            man.at[i, "sha1"] = hashlib.sha1(r.content).hexdigest()
            man.at[i, "arquivo"] = str(arq.relative_to(DESTINO))
        except requests.RequestException as e:
            man.at[i, "status"] = f"erro: {e}"[:120]
        time.sleep(0.5)
    man.to_csv(pasta / "_manifesto.csv", index=False)
    resumo = man[man.parece_rreo & man.no_periodo].groupby("ano")["bimestre"].nunique()
    log.info("%s: %s links avaliados; bimestres por ano encontrados: %s", uf, len(man), resumo.to_dict())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf")
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--anos", nargs=2, type=int, default=(2000, 2015))
    ap.add_argument("--profundidade", type=int, default=2)
    ap.add_argument("--listar", action="store_true", help="só gera o manifesto, sem baixar")
    a = ap.parse_args()
    cat = pd.read_csv(REF / "rreo_portais.csv").fillna("")
    alvos = cat if a.todos else cat[cat.uf == a.uf]
    for _, c in alvos.iterrows():
        if not c.url:
            log.info("%s: sem URL no catálogo; preencher dados/00_referencia/rreo_portais.csv", c.uf)
            continue
        baixar(c.uf, c.tipo, c.url, tuple(a.anos), a.profundidade, a.listar)
