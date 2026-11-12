"""Extrai do RREO em PDF (ou XLS) as linhas principais do Balanço Orçamentário e a RCL.

Para cada arquivo baixado por 40_rreo_baixar.py, a rotina:
  1. lê o texto das páginas (pdfplumber); PDF sem texto é marcado como "sem_texto"
     e precisa de OCR antes (ver docs/rreo_historico.md);
  2. localiza o Balanço Orçamentário e separa receitas de despesas;
  3. em cada linha-alvo, lê todos os números e escolhe o valor acumulado até o
     bimestre usando a identidade contábil da própria linha:
        receita:  previsão atualizada = realizado até o bimestre + saldo a realizar
        despesa:  dotação atualizada  = liquidado até o bimestre + saldo
     Se a identidade não fecha, usa a posição padrão da coluna e marca a linha;
  4. localiza o demonstrativo da RCL e pega o total dos últimos 12 meses
     (o valor que é igual à soma dos 12 meses anteriores).

Uso:
    python scripts/41_rreo_extrair.py --uf MT
    python scripts/41_rreo_extrair.py --todos
    python scripts/41_rreo_extrair.py --arquivo dados/01_bruto/rreo_rgf_portais/MT/2008/MT_2008_b6.pdf --mostrar

Saída: dados/02_intermediario/rreo_pdf_extraido.csv (formato longo) e um log por arquivo.
"""
from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import pandas as pd

from _util import BRUTO, RAIZ, log

ORIGEM = BRUTO / "rreo_rgf_portais"
SAIDA = RAIZ / "dados" / "02_intermediario" / "rreo_pdf_extraido.csv"

RECEITAS = {
    "receita_corrente": r"^RECEITAS? CORRENTES?\b",
    "receita_tributaria": r"^(RECEITA TRIBUTARIA|IMPOSTOS, TAXAS E CONTRIBUICOES DE MELHORIA)",
    "transferencias_correntes": r"^TRANSFERENCIAS CORRENTES",
    "receita_capital": r"^RECEITAS? DE CAPITAL\b",
    "operacoes_credito": r"^OPERACOES DE CREDITO",
}
DESPESAS = {
    "despesa_corrente": r"^DESPESAS? CORRENTES?\b",
    "pessoal": r"^PESSOAL E ENCARGOS SOCIAIS",
    "juros": r"^JUROS E ENCARGOS DA DIVIDA",
    "custeio": r"^OUTRAS DESPESAS CORRENTES",
    "despesa_capital": r"^DESPESAS? DE CAPITAL\b",
    "investimento": r"^INVESTIMENTOS",
    "inversoes": r"^INVERSOES FINANCEIRAS",
    "amortizacao": r"^AMORTIZACAO DA DIVIDA",
}
POSICAO_PADRAO = {"receita": 4, "despesa": 6}   # leiaute do Manual de Demonstrativos (2005-2014)
RX_NUM = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?$|^\(?-?\d+(?:,\d+)?\)?$")


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def para_numero(tok: str) -> float | None:
    if tok in {"-", "–", "—"}:
        return 0.0
    if not RX_NUM.match(tok):
        return None
    neg = tok.startswith("(") or tok.startswith("-")
    v = float(tok.strip("()-").replace(".", "").replace(",", "."))
    return -v if neg else v


def separar(linha: str) -> tuple[str, list[float]]:
    """Divide a linha em rótulo e números (a partir do primeiro token numérico)."""
    toks = linha.split()
    for i, t in enumerate(toks):
        # “(I)”, “(II)”, “(a)” e similares fazem parte do rótulo
        if para_numero(t) is not None and not re.fullmatch(r"\(?[IVXLa-h]+\)?", t):
            nums = [para_numero(x) for x in toks[i:]]
            return " ".join(toks[:i]), [n for n in nums if n is not None]
    return linha, []


def escolher(vals: list[float], tipo: str) -> tuple[float | None, str]:
    if len(vals) < 3:
        return None, "poucos_valores"
    saldo = vals[-1]
    for j in range(len(vals) - 2, 0, -1):          # de trás para frente: prefere o liquidado
        for i in range(j):
            a, c = vals[i], vals[j]
            if abs(c) < 1000 and abs(a) > 1e6:     # descarta colunas de percentual
                continue
            if abs(a - (c + saldo)) <= max(1.0, 1e-7 * abs(a)) and abs(c) > 0:
                return c, "identidade"
    k = POSICAO_PADRAO[tipo]
    return (vals[k], "posicao_padrao") if len(vals) > k else (None, "sem_regra")


def rcl_total(vals: list[float]) -> tuple[float | None, str]:
    if len(vals) >= 13:
        for k in range(12, len(vals)):
            if abs(sum(vals[k - 12:k]) - vals[k]) <= max(1.0, 1e-4 * abs(vals[k])):
                return vals[k], "identidade"
        return vals[12], "posicao_padrao"
    return (vals[-1], "ultimo_valor") if vals else (None, "sem_valores")


def paginas_texto(arq: Path) -> list[str]:
    if arq.suffix.lower() == ".pdf":
        import pdfplumber
        with pdfplumber.open(arq) as pdf:
            return [p.extract_text() or "" for p in pdf.pages]
    folhas = pd.read_excel(arq, sheet_name=None, header=None)  # .xls/.xlsx
    paginas = []
    for df in folhas.values():
        linhas = []
        for _, r in df.iterrows():
            cel = [str(x) for x in r if pd.notna(x)]
            linhas.append(" ".join(c if not isinstance(c, float) else f"{c:.2f}".replace(".", ",") for c in cel))
        paginas.append("\n".join(linhas))
    return paginas


def unidade(texto: str) -> int:
    t = norm(texto)
    return 1000 if re.search(r"R\$ ?MILHARES|EM MILHARES|R\$ ?1\.000|R\$ MIL\b", t) else 1


def extrair(arq: Path, mostrar: bool = False) -> tuple[list[dict], str]:
    paginas = paginas_texto(arq)
    if not any(p.strip() for p in paginas):
        return [], "sem_texto"
    uf, ano, bim = arq.stem.split("_")
    base = {"uf": uf, "ano": int(ano), "bimestre": int(bim[1:]), "arquivo": arq.name}
    regs = []

    # Balanço orçamentário: da primeira página com o título até, no máximo, 3 páginas depois
    ini = next((i for i, p in enumerate(paginas) if "BALANCO ORCAMENTARIO" in norm(p)
                and "SIMPLIFICADO" not in norm(p)[:300]), None)
    if ini is not None:
        bloco = "\n".join(paginas[ini:ini + 3])
        mult = unidade(bloco)
        linhas = [norm(l) for l in bloco.splitlines() if l.strip()]
        corte = next((i for i, l in enumerate(linhas) if "DOTACAO" in l and i > 5), len(linhas))
        for secao, alvos, tipo in [(linhas[:corte], RECEITAS, "receita"), (linhas[corte:], DESPESAS, "despesa")]:
            for var, rx in alvos.items():
                for l in secao:
                    rot, vals = separar(l)
                    if re.search(rx, rot) and "INTRA" not in rot and vals:
                        v, metodo = escolher(vals, tipo)
                        regs.append({**base, "variavel": var, "valor": None if v is None else v * mult,
                                     "metodo": metodo, "n_valores": len(vals), "pagina": ini + 1,
                                     "linha": l[:160]})
                        if mostrar:
                            print(f"{var:26s} {metodo:15s} {v}  <- {l[:110]}")
                        break
    # RCL
    pr = next((i for i, p in enumerate(paginas) if "RECEITA CORRENTE LIQUIDA" in norm(p)
               and ("ULTIMOS" in norm(p) or "12 MESES" in norm(p))), None)
    if pr is not None:
        mult = unidade(paginas[pr])
        for l in (norm(x) for x in paginas[pr].splitlines()):
            rot, vals = separar(l)
            if rot.startswith("RECEITA CORRENTE LIQUIDA") and len(vals) >= 6:
                v, metodo = rcl_total(vals)
                regs.append({**base, "variavel": "rcl", "valor": None if v is None else v * mult,
                             "metodo": metodo, "n_valores": len(vals), "pagina": pr + 1, "linha": l[:160]})
                if mostrar:
                    print(f"{'rcl':26s} {metodo:15s} {v}  <- {l[:110]}")
                break
    status = "ok" if regs else "balanco_nao_encontrado"
    return regs, status


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf")
    ap.add_argument("--todos", action="store_true")
    ap.add_argument("--arquivo")
    ap.add_argument("--mostrar", action="store_true", help="imprime as linhas encontradas")
    a = ap.parse_args()
    if a.arquivo:
        arqs = [Path(a.arquivo)]
    else:
        pasta = ORIGEM if a.todos else ORIGEM / a.uf
        arqs = sorted(p for p in pasta.rglob("*_b[1-6].*") if p.suffix.lower() in (".pdf", ".xls", ".xlsx"))
    todos, relatorio = [], []
    for arq in arqs:
        try:
            regs, status = extrair(arq, a.mostrar)
        except Exception as e:  # PDF corrompido, protegido etc.
            regs, status = [], f"erro: {e}"[:120]
        todos += regs
        relatorio.append({"arquivo": str(arq), "status": status, "variaveis": len(regs),
                          "fallbacks": sum(r["metodo"] != "identidade" for r in regs)})
    if todos:
        novo = pd.DataFrame(todos)
        if SAIDA.exists() and not a.arquivo:
            antigo = pd.read_csv(SAIDA)
            antigo = antigo[~antigo.arquivo.isin(novo.arquivo)]
            novo = pd.concat([antigo, novo])
        SAIDA.parent.mkdir(parents=True, exist_ok=True)
        if not a.arquivo:
            novo.to_csv(SAIDA, index=False)
    rel = pd.DataFrame(relatorio)
    if not a.arquivo and not rel.empty:
        rel.to_csv(SAIDA.with_name("rreo_pdf_relatorio_extracao.csv"), index=False)
    log.info("Arquivos: %s | status: %s", len(rel), rel["status"].value_counts().to_dict() if len(rel) else {})
