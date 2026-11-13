"""Extrai do RREO em PDF (ou XLS) as linhas principais do Balanço Orçamentário e a RCL.

Para cada arquivo baixado por 40_rreo_baixar.py, a rotina:
  1. lê o texto das páginas (pdfplumber); PDF sem texto é marcado como "sem_texto"
     e precisa de OCR antes (ver docs/rreo_historico.md);
  2. conserta o que a leitura do PDF costuma estragar: números partidos por espaço
     ("2 .334.367", "1 1.080.643"), números colados ("1.234,565.678,90"), rótulos
     com as palavras grudadas ou com letras espaçadas, numeração no início da linha;
  3. localiza o Balanço Orçamentário e, em cada linha-alvo, lê todos os números e
     escolhe o valor acumulado até o bimestre pela identidade contábil da linha:
        receita:  previsão atualizada = realizado até o bimestre + saldo a realizar
        despesa:  dotação atualizada  = empenhado (ou liquidado) até o bimestre + saldo
     Na despesa, quando a identidade cai no empenhado, procura à direita o liquidado
     (o valor que, somado aos restos a pagar não processados, dá o empenhado).
     Se nada fecha, usa a posição padrão da coluna e marca a linha;
  4. localiza o demonstrativo da RCL, junta as linhas da RCL na página (a tabela
     de 12 meses costuma vir partida em duas) e pega o total dos últimos 12 meses,
     o valor igual à soma dos 12 anteriores.

O RREO pode vir num arquivo só ou em partes (um arquivo por anexo); cada arquivo é
lido inteiro, e no fim fica, para cada variável, a leitura que fechou pela identidade.

Uso:
    python scripts/41_rreo_extrair.py --uf MT
    python scripts/41_rreo_extrair.py --todos
    python scripts/41_rreo_extrair.py --arquivo dados/01_bruto/rreo_rgf_portais/MT/2008/MT_2008_b6.pdf --mostrar

Saídas:
    dados/02_intermediario/rreo_pdf_extraido.csv            formato longo, uma linha por variável
    dados/02_intermediario/rreo_pdf_relatorio_extracao.csv  status de cada arquivo
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

# Expressões sobre o rótulo compacto (só letras, sem espaços nem acentos)
RECEITAS = {
    "receita_corrente": r"^RECEITAS?CORRENTES?(?!LIQUIDA)",
    "receita_tributaria": r"^(RECEITATRIBUTARIA|IMPOSTOSTAXASECONTRIBUICOESDEMELHORIA)",
    "transferencias_correntes": r"^TRANSFERENCIASCORRENTES",
    "receita_capital": r"^RECEITAS?DECAPITAL",
    "operacoes_credito": r"^OPERACOESDECREDITO",
}
DESPESAS = {
    "despesa_corrente": r"^DESPESAS?CORRENTES?",
    "pessoal": r"^PESSOALEENCARGOS?SOCIA(IS|L)",
    "juros": r"^JUROSEENCARGOSDADIVIDA",
    "custeio": r"^OUTRASDESPESASCORRENTES",
    "despesa_capital": r"^DESPESAS?DECAPITAL",
    "investimento": r"^INVESTIMENTOS",
    "inversoes": r"^INVERSOESFINANCEIRAS",
    "amortizacao": r"^AMORTIZACAODADIVIDA",
}
TITULOS_BALANCO = ("BALANCOORCAMENTARIO", "PREVISAOEREALIZACAODARECEITAEDADESPESA")
POSICAO_PADRAO = {"receita": 4, "despesa": 6}   # leiaute do Manual de Demonstrativos (2005-2014)
RX_NUM = re.compile(r"^\(?-?\d{1,3}(?:\.\d{3})*(?:,\d+)?\)?$|^\(?-?\d+(?:,\d+)?\)?$")
RX_ENUM = re.compile(r"^(?:(?:\(?\d{1,2}(?:\.\d{1,2})*\)?|\(?[IVX]{1,4}\)?)[\s.\-)]+)+(?=[A-Z(])")


def norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().upper()


def compacto(t: str) -> str:
    return re.sub(r"[^A-Z]", "", norm(t))


def para_numero(tok: str) -> float | None:
    if tok in {"-", "–", "—"}:
        return 0.0
    if not RX_NUM.match(tok):
        return None
    neg = tok.startswith("(") or tok.startswith("-")
    v = float(tok.strip("()-").replace(".", "").replace(",", "."))
    return -v if neg else v


def consertar_numeros(linha: str) -> str:
    """Remonta números que a extração do PDF partiu ou colou."""
    linha = re.sub(r"\[[^\]]*\]", " ", linha)                    # fórmulas “[=3+8+11]”
    linha = re.sub(r"^(\d+)(?=[A-Z])", r"\1 ", linha)            # “27III - RECEITA”
    linha = re.sub(r"(?<=[A-Z)])(?=\d)", " ", linha)              # “SOCIAIS1.199.885”
    linha = re.sub(r"\(\s+", "(", linha)
    linha = re.sub(r"\s+\)", ")", linha)
    linha = re.sub(r"(\d)\s+(?=[.,]\d)", r"\1", linha)          # "2 .334.367"
    linha = re.sub(r"(,\d{2})(?=\d)", r"\1 ", linha)             # "1.234,565.678,90"
    toks, saida = linha.split(" "), []
    for t in toks:
        # "1 1.080.643" -> "11.080.643"; "9 7,47" -> "97,47": dígito solto antes de número
        # formatado cujo primeiro grupo ficou curto
        if (saida and re.fullmatch(r"\(?\d{1,2}", saida[-1]) and re.match(r"\d{1,2}[.,]", t)
                and len(saida[-1].lstrip("(")) + len(re.match(r"\d+", t).group()) <= 3
                and RX_NUM.match(saida[-1] + t)):
            saida[-1] += t
        else:
            saida.append(t)
    return " ".join(saida)


def separar(linha: str) -> tuple[str, list[float]]:
    """Divide a linha em rótulo e números (a partir do primeiro token numérico)."""
    linha = RX_ENUM.sub("", linha)
    toks = linha.split()
    for i, t in enumerate(toks):
        # “(I)”, “(II)”, “(a)” e similares fazem parte do rótulo, e o hífen de
        # “(I - II)” também: traço só vale zero se vier seguido de número
        if t in {"-", "–", "—"} and i + 1 < len(toks) and para_numero(toks[i + 1]) is None:
            continue
        if para_numero(t) is not None and not re.fullmatch(r"\(?[IVXLa-h]+\)?", t):
            nums = [para_numero(x) for x in toks[i:]]
            return " ".join(toks[:i]), [n for n in nums if n is not None]
    return linha, []


def perto(a: float, b: float) -> bool:
    return abs(a - b) <= max(2.0, 1e-7 * abs(a))


def escolher(vals: list[float], tipo: str) -> tuple[float | None, str]:
    if len(vals) < 3:
        return None, "poucos_valores"
    saldo = vals[-1]
    for j in range(len(vals) - 2, 0, -1):          # de trás para frente: prefere o acumulado
        for i in range(j):
            a, c = vals[i], vals[j]
            if abs(c) < 1000 and abs(a) > 1e6:     # descarta colunas de percentual
                continue
            if c and perto(a, c + saldo):
                if tipo == "despesa":
                    # identidade no empenhado (ou no total executado, que no 6º bimestre
                    # é igual a ele): o liquidado é o valor que, somado a um valor menor
                    # da linha (restos a pagar não processados), dá o empenhado
                    resto = [k for k in range(i + 1, len(vals) - 1) if k != j]
                    for k in resto:
                        if 0 < vals[k] <= c and any(m != k and 0 <= vals[m] < vals[k]
                                                    and perto(c, vals[k] + vals[m]) for m in resto):
                            return vals[k], "identidade"
                return c, "identidade"
    k = POSICAO_PADRAO[tipo]
    return (vals[k], "posicao_padrao") if len(vals) > k else (None, "sem_regra")


def rcl_total(vals: list[float]) -> tuple[float | None, str]:
    if len(vals) >= 13:
        for k in range(12, len(vals)):
            if abs(sum(vals[k - 12:k]) - vals[k]) <= max(12.0, 1e-6 * abs(vals[k])):
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
            cel = [f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                   if isinstance(x, (int, float)) else str(x) for x in r if pd.notna(x)]
            linhas.append(" ".join(cel))
        paginas.append("\n".join(linhas))
    return paginas


def tem_texto(paginas: list[str]) -> bool:
    t = "".join(paginas)
    return len(re.sub(r"\(cid:\d+\)|\s", "", t)) > 200 and t.count("(cid:") < len(t) / 50


def unidade(texto: str) -> int:
    t = norm(texto)
    return 1000 if re.search(r"R\$ ?MILHARES|EM MILHARES|R\$ ?1\.000|R\$ MIL\b|EM R\$ ?MIL\b", t) else 1


def linhas_de(texto: str) -> list[tuple[str, str, list[float]]]:
    """(linha normalizada, rótulo compacto, números) de cada linha do texto.

    Em alguns leiautes o rótulo fica numa linha e os números na seguinte; nesse
    caso as duas viram uma só. Quando o rótulo quebra em duas linhas (“PESSOAL E”
    e “ENCARGOS SOCIAIS 1.234”), a linha com números ganha uma segunda versão,
    com o rótulo emendado, para a busca.
    """
    saida = []
    for bruta in texto.splitlines():
        l = consertar_numeros(norm(bruta))
        if not l:
            continue
        rot, vals = separar(l)
        comp = compacto(rot)
        anterior = saida[-1] if saida else None
        if anterior and anterior[1] and not anterior[2] and vals:
            if not comp:
                saida[-1] = (f"{anterior[0]} {l}", anterior[1], vals)
                continue
            saida.append((f"{anterior[0]} {l}", anterior[1] + comp, vals))
        elif anterior and anterior[2] and comp and not vals:
            # rótulo centralizado na célula: o fim dele vem depois dos números
            saida.append((f"{anterior[0]} {l}", anterior[1] + comp, anterior[2]))
        saida.append((l, comp, vals))
    return saida


def extrair(arq: Path, mostrar: bool = False) -> tuple[list[dict], str]:
    paginas = paginas_texto(arq)
    if not tem_texto(paginas):
        return [], "sem_texto"
    uf, ano, bim = re.match(r"([A-Z]{2})_(\d{4})_b([1-6])", arq.stem).groups()
    base = {"uf": uf, "ano": int(ano), "bimestre": int(bim), "arquivo": arq.name}
    regs = []
    por_pagina = [linhas_de(p) for p in paginas]

    def registrar(var, v, metodo, n, pagina, linha, mult):
        regs.append({**base, "variavel": var, "valor": None if v is None else v * mult,
                     "metodo": metodo, "n_valores": n, "pagina": pagina + 1, "linha": linha[:160]})
        if mostrar:
            print(f"{var:26s} {metodo:15s} {v}  <- {linha[:110]}")

    # Balanço orçamentário: primeira página com o título e com receita ou despesa
    # corrente com números (evita sumário e demonstrativo simplificado), mais as
    # três seguintes, onde a tabela costuma continuar
    def eh_balanco(i):
        comp = compacto(paginas[i])
        if not any(t in comp for t in TITULOS_BALANCO) or "SIMPLIFICADO" in compacto(paginas[i][:300]):
            return False
        return any(re.match(r"^(RECEITAS?|DESPESAS?)CORRENTES?(?!LIQUIDA)", c) and len(v) >= 3
                   for _, c, v in por_pagina[i])
    ini = next((i for i in range(len(paginas)) if eh_balanco(i)), None)
    if ini is not None:
        mult = unidade("\n".join(paginas[ini:ini + 4]))
        bloco = [(i, x) for i in range(ini, min(ini + 4, len(paginas))) for x in por_pagina[i]]
        for alvos, tipo in [(RECEITAS, "receita"), (DESPESAS, "despesa")]:
            for var, rx in alvos.items():
                for pag, (l, comp, vals) in bloco:
                    if re.search(rx, comp) and "INTRA" not in comp and len(vals) >= 3:
                        v, metodo = escolher(vals, tipo)
                        registrar(var, v, metodo, len(vals), pag, l, mult)
                        break

    # RCL: junta as linhas da RCL de cada página (e da seguinte, se a tabela continua)
    for i in range(len(paginas)):
        def linhas_rcl(k):
            return [(l, v) for l, c, v in por_pagina[k]
                    if c.startswith("RECEITACORRENTELIQUIDA") and "AJUSTADA" not in c and v]
        achadas = linhas_rcl(i)
        if not achadas:
            continue
        vals = [x for _, v in achadas for x in v]
        if len(vals) < 13 and i + 1 < len(paginas):
            vals += [x for _, v in linhas_rcl(i + 1) for x in v]
        if len(vals) < 6:
            continue
        v, metodo = rcl_total(vals)
        registrar("rcl", v, metodo, len(vals), i, " / ".join(l for l, _ in achadas), unidade(paginas[i]))
        if metodo == "identidade":
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
        arqs = sorted(p for p in pasta.rglob("*_b[1-6]*") if p.suffix.lower() in (".pdf", ".xls", ".xlsx"))
    todos, relatorio = [], []
    for arq in arqs:
        try:
            regs, status = extrair(arq, a.mostrar)
        except Exception as e:  # PDF corrompido, protegido etc.
            regs, status = [], f"erro: {e}"[:120]
        todos += regs
        relatorio.append({"arquivo": str(arq.relative_to(ORIGEM)) if arq.is_relative_to(ORIGEM) else str(arq),
                          "status": status, "variaveis": len(regs),
                          "fallbacks": sum(r["metodo"] != "identidade" for r in regs)})
    if todos and not a.arquivo:
        novo = pd.DataFrame(todos)
        if SAIDA.exists():
            antigo = pd.read_csv(SAIDA)
            antigo = antigo[~antigo.arquivo.isin(novo.arquivo)]
            novo = pd.concat([antigo, novo])
        # RREO em partes, ou mais de uma leitura da RCL: fica a que fechou pela identidade
        novo = (novo.assign(_ordem=(novo["metodo"] != "identidade") | novo["valor"].isna())
                    .sort_values(["_ordem", "arquivo"])
                    .drop_duplicates(["uf", "ano", "bimestre", "variavel"])
                    .drop(columns="_ordem").sort_values(["uf", "ano", "bimestre", "variavel"]))
        SAIDA.parent.mkdir(parents=True, exist_ok=True)
        novo.to_csv(SAIDA, index=False)
    rel = pd.DataFrame(relatorio)
    if not a.arquivo and not rel.empty:
        rel.to_csv(SAIDA.with_name("rreo_pdf_relatorio_extracao.csv"), index=False)
    log.info("Arquivos: %s | status: %s", len(rel), rel["status"].value_counts().to_dict() if len(rel) else {})
