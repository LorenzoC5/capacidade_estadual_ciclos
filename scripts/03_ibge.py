"""Dados macroeconômicos estaduais do IBGE (API SIDRA e FTP das Contas Regionais).

Define o ciclo econômico de cada UF (PIB anual, atividade mensal, desemprego)
e os denominadores (população, PIB nominal).

Estratégia:
  a) Contas Regionais: a API de agregados não tem pesquisa com esse nome. A única
     tabela por UF no SIDRA é a 5938, que está na pesquisa "Produto Interno Bruto
     dos Municípios" e só traz valores correntes. Volume e preço por UF saem das
     planilhas da edição mais recente no FTP (ftp.ibge.gov.br/Contas_Regionais/
     <edição>/xls/): o pacote "Especiais" (PIB e VAB correntes, participações e
     séries encadeadas de volume) e o pacote "Conta da Produção" (VBP, consumo
     intermediário e VAB por atividade, com índice de volume e índice de preço,
     isto é, o deflator). Os zips ficam em ibge/contas_regionais/<edição>/ e as
     tabelas viram dois CSVs em formato longo.
  b) Baixa uma lista fixa de tabelas conjunturais do SIDRA. Antes de baixar, grava
     o metadado de cada tabela em ibge/_metadados para conferência do conteúdo.

Uso:
    python scripts/03_ibge.py
"""
from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile

import pandas as pd

from _util import BRUTO, REF, get, ja_existe, log, salvar

SIDRA = "https://apisidra.ibge.gov.br/values"
AGREG = "https://servicodados.ibge.gov.br/api/v3/agregados"
FTP_CR = "https://ftp.ibge.gov.br/Contas_Regionais"

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


# Contas Regionais (FTP). As planilhas .xls perderam os acentos na origem (vêm
# como caractere de substituição), então UFs e atividades são identificadas por
# uma chave sem acentos e pela posição da aba, e os nomes gravados são os corretos.
ATIVIDADES_CR = [
    "Total das Atividades",
    "Agropecuária",
    "Indústrias extrativas",
    "Indústrias de transformação",
    "Eletricidade e gás, água, esgoto, atividades de gestão de resíduos e descontaminação",
    "Construção",
    "Comércio e reparação de veículos automotores e motocicletas",
    "Transporte, armazenagem e correio",
    "Informação e comunicação",
    "Atividades financeiras, de seguros e serviços relacionados",
    "Atividades imobiliárias",
    "Administração, defesa, educação e saúde públicas e seguridade social",
    "Outros serviços",
]
# Tabelas do pacote "Especiais" com território nas linhas e anos nas colunas.
ESPECIAIS_CR = {
    1: "PIB a preços correntes (R$ milhões)",
    2: "Participação no PIB do Brasil (%)",
    3: "Série encadeada do volume do PIB (2002 = 100)",
    4: "VAB a preços correntes (R$ milhões)",
    5: "Série encadeada do volume do VAB (2002 = 100)",
    6: "Participação no VAB do Brasil (%)",
}
AGREGADOS_CP = {"valor bruto da producao": "VBP", "consumo intermediario": "CI",
                "valor adicionado bruto": "VAB"}
COLUNAS_CP = ["valor_ano_anterior", "indice_volume", "valor_precos_ano_anterior",
              "indice_preco", "valor_corrente"]


def chave_nome(nome) -> str:
    """Chave sem acentos que casa "Rondônia" com o "Rond?nia" das planilhas."""
    txt = unicodedata.normalize("NFKD", str(nome).strip())
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"[^a-z]+", "?", txt.lower())


def territorios_cr() -> dict[str, tuple[str, str, str]]:
    """chave -> (nome, sigla, nível) para Brasil, grandes regiões e UFs."""
    terr = {chave_nome("Brasil"): ("Brasil", "BR", "Brasil")}
    for reg in ["Norte", "Nordeste", "Sudeste", "Sul", "Centro-Oeste"]:
        terr[chave_nome(reg)] = (reg, "", "Grande Região")
        terr[chave_nome(f"Região {reg}")] = (reg, "", "Grande Região")
    for _, uf in pd.read_csv(REF / "ufs.csv").iterrows():
        terr[chave_nome(uf.nome)] = (uf.nome, uf.sigla, "UF")
    return terr


def edicao_contas_regionais() -> tuple[str, str] | None:
    """Edição mais recente no FTP que tenha o pacote Especiais da série 2002."""
    pagina = get(f"{FTP_CR}/", como_json=False, timeout=60)
    if not pagina:
        return None
    edicoes = sorted(set(re.findall(r'href="(\d{4})/"', pagina.decode("utf-8", "replace"))),
                     reverse=True)
    for edicao in edicoes:
        lista = get(f"{FTP_CR}/{edicao}/xls/", como_json=False, timeout=60)
        if lista and f"Especiais_2002_{edicao}_xls.zip".encode() in lista:
            return edicao, f"{FTP_CR}/{edicao}/xls"
    return None


def baixar_zip_cr(url: str, destino) -> zipfile.ZipFile | None:
    if not ja_existe(destino):
        conteudo = get(url, como_json=False)
        if not conteudo:
            return None
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(conteudo)
    return zipfile.ZipFile(destino)


def ler_xls(arquivo: zipfile.ZipFile, nome: str) -> dict[str, pd.DataFrame]:
    """Todas as abas de um .xls do zip (exige o pacote xlrd)."""
    return pd.read_excel(io.BytesIO(arquivo.read(nome)), sheet_name=None, header=None)


def num_aba(nome_aba: str) -> int | None:
    """"Tabela5.3" -> 3; abas sem sufixo (sumário ou tabela única) -> None."""
    m = re.search(r"\.(\d+)$", nome_aba)
    return int(m.group(1)) if m else None


def especiais_longo(arquivo: zipfile.ZipFile, edicao: str) -> pd.DataFrame:
    terr = territorios_cr()
    linhas = []
    for tabela, variavel in ESPECIAIS_CR.items():
        nome = f"tab{tabela:02d}.xls"
        if nome not in arquivo.namelist():
            log.warning("Contas Regionais %s: %s ausente no pacote Especiais", edicao, nome)
            continue
        abas = ler_xls(arquivo, nome)
        for aba, df in abas.items():
            k = num_aba(aba)
            if k is None and len(abas) > 1:
                continue  # sumário
            if k:
                atividade = ATIVIDADES_CR[k - 1]
            else:
                atividade = ATIVIDADES_CR[0] if tabela >= 4 else ""
            anos = pd.to_numeric(df.iloc[:, 1], errors="coerce")
            linha_anos = df.index[anos == 2002]
            if linha_anos.empty:
                log.warning("Contas Regionais tab%02d/%s: linha de anos não encontrada", tabela, aba)
                continue
            cab = pd.to_numeric(df.loc[linha_anos[0]].iloc[1:], errors="coerce")
            for _, r in df.loc[linha_anos[0] + 1:].iterrows():
                t = terr.get(chave_nome(r.iloc[0]))
                if not t:
                    continue
                for col, ano in cab.items():
                    if pd.notna(ano) and pd.notna(r[col]):
                        linhas.append({"edicao": edicao, "tabela": tabela, "variavel": variavel,
                                       "atividade": atividade, "territorio": t[0], "sigla": t[1],
                                       "nivel": t[2], "ano": int(ano), "valor": float(r[col])})
    return pd.DataFrame(linhas)


def conta_producao_longo(arquivo: zipfile.ZipFile, edicao: str) -> pd.DataFrame:
    """Um arquivo por território; o território vem do título do sumário, porque o
    rótulo dentro das abas das grandes regiões repete "Região Norte" por engano."""
    terr = territorios_cr()
    linhas = []
    for nome in sorted(n for n in arquivo.namelist() if n.lower().endswith(".xls")):
        abas = ler_xls(arquivo, nome)
        sumario = next((df for aba, df in abas.items() if num_aba(aba) is None), None)
        titulo = str(sumario.iat[1, 0]) if sumario is not None else ""
        partes = [p.strip() for p in titulo.split(" - ")]
        territorio = terr.get(chave_nome(partes[-2])) if len(partes) >= 3 else None
        if not territorio:
            log.warning("Contas Regionais %s: território não reconhecido no título %r", nome, titulo)
            continue
        divergentes = 0
        for aba, df in abas.items():
            k = num_aba(aba)
            if k is None:
                continue  # sumário
            agregado = None
            for i in range(len(df)):
                c0 = df.iat[i, 0]
                if isinstance(c0, str):
                    rotulo = chave_nome(c0).replace("?", " ")
                    achado = next((v for p, v in AGREGADOS_CP.items() if rotulo.startswith(p)), None)
                    if achado:
                        agregado = achado
                        if terr.get(chave_nome(df.iat[i + 1, 0])) != territorio:
                            divergentes += 1
                        continue
                ano = pd.to_numeric(c0, errors="coerce")
                if agregado and pd.notna(ano) and 1990 < ano < 2100:
                    valores = dict(zip(COLUNAS_CP, df.iloc[i, 1:6].tolist()))
                    linhas.append({"edicao": edicao, "agregado": agregado,
                                   "atividade": ATIVIDADES_CR[k - 1], "territorio": territorio[0],
                                   "sigla": territorio[1], "nivel": territorio[2],
                                   "ano": int(ano), **valores})
        if divergentes:
            log.info("Contas Regionais %s: %s blocos com rótulo interno diferente de %s; "
                     "usado o título do arquivo", nome, divergentes, territorio[0])
    return pd.DataFrame(linhas)


def contas_regionais():
    destino_esp = BRUTO / "ibge" / "contas_regionais_especiais.csv"
    destino_cp = BRUTO / "ibge" / "contas_regionais_conta_producao.csv"
    if ja_existe(destino_esp) and ja_existe(destino_cp):
        return
    achada = edicao_contas_regionais()
    if not achada:
        log.warning("Contas Regionais: nenhuma edição encontrada em %s", FTP_CR)
        return
    edicao, base = achada
    pasta = BRUTO / "ibge" / "contas_regionais" / edicao
    for pacote, destino, montar in [("Especiais", destino_esp, especiais_longo),
                                    ("Conta_da_Producao", destino_cp, conta_producao_longo)]:
        if ja_existe(destino):
            continue
        nome_zip = f"{pacote}_2002_{edicao}_xls.zip"
        arquivo = baixar_zip_cr(f"{base}/{nome_zip}", pasta / nome_zip)
        if not arquivo:
            log.warning("Contas Regionais: falha ao baixar %s", nome_zip)
            continue
        df = montar(arquivo, edicao)
        n = salvar(df, destino)
        ufs_ok = df.loc[df["nivel"] == "UF", "sigla"].nunique() if n else 0
        log.info("Contas Regionais %s (edição %s): %s linhas, %s UFs", pacote, edicao, n, ufs_ok)


if __name__ == "__main__":
    contas_regionais()
    for t, rotulo in TABELAS_FIXAS.items():
        baixar_tabela(t, rotulo)
