# Capacidade estadual de amortização de ciclos econômicos

Pasta de dados do projeto em parceria com a SEFAZ-MT. O tema reúne quatro frentes: a capacidade de política fiscal dos governos estaduais, o multiplicador fiscal estadual, a reação dos estados aos ciclos econômicos e o tamanho do colchão de liquidez que permitiria suavizar esses ciclos, com atenção ao papel da LRF.

O ponto de partida combinado com o orientador são três perguntas: (i) a poupança estadual é pró-cíclica?; (ii) como os estados reagiram às crises recentes?; (iii) estados mais endividados ou com menor poupança tiveram resultados piores nessas crises?

## Escopo de dados acertado com o orientador

O grupo trabalha só com dados públicos: a SEFAZ-MT não vai enviar dados internos para esta parte do projeto. Por isso o saldo de caixa diário ou mensal fica fora; o colchão de liquidez é medido pelo que é publicado (disponibilidade de caixa do RGF, Anexo 5, balanço patrimonial da DCA e, a partir de 2018, a MSC mensal). Dívida por contrato e ICMS por setor também ficam fora.

O período de análise começa em 2000, com a LRF, o que permite comparar crise e não crise em pelo menos três episódios: 2003, 2008-09 e 2015-16, além de 2020. As variáveis centrais são a poupança corrente, a despesa com pessoal, o investimento e as despesas de capital, a dívida consolidada (RGF e PAF) e o custo do serviço da dívida, que o orientador sugeriu acompanhar ao longo das crises.

A API do SICONFI só tem o RREO e o RGF dos estados a partir de 2015. Para 2000 a 2014 há duas saídas, descritas em `docs/downloads_manuais.md`: as séries anuais do Tesouro (Execução Orçamentária de Estados e FINBRA histórico) e os relatórios em PDF publicados no portal de cada secretaria de Fazenda.

## Como a pasta está organizada

```
capacidade_estadual_ciclos/
├── README.md                    este arquivo
├── catalogo_bases.csv           uma linha por base: fonte, cobertura, variáveis, pergunta que atende
├── requirements.txt
├── scripts/
│   ├── 00_baixar_tudo.py        roda a coleta inteira, em ordem
│   ├── 01_siconfi.py            RREO, RGF, DCA e MSC dos 27 estados (API do Tesouro)
│   ├── 02_tesouro.py            transferências, SADIPEM, CAPAG, boletim, garantias, dívida
│   ├── 03_ibge.py               PIB estadual, população, PNAD, PIM, PMC, PMS
│   ├── 04_bcb.py                IPCA, Selic, IBC-Br, IBCR regional, fiscais estaduais
│   ├── 05_ipeadata.py           séries fiscais estaduais longas (antes do SICONFI)
│   ├── 10_consolidar_siconfi.py empilha os arquivos brutos do SICONFI
│   ├── 20_passo1_ajuste_crises.py  passo 1: o que cada estado cortou em cada crise
│   ├── 30_corte_se_paga.py      quanto de cada real cortado o estado de fato economiza
│   ├── 40_rreo_baixar.py        RREO 2000-2014 nos portais estaduais (PDF/XLS)
│   ├── 41_rreo_extrair.py       lê Balanço Orçamentário e RCL dos PDFs
│   ├── 42_rreo_serie_continua.py une PDFs e API numa série 2000 em diante
│   └── _util.py                 requisições, paginação, gravação
├── dados/
│   ├── 00_referencia/           UFs, datas das crises, marcos legais (já preenchidos)
│   ├── 01_bruto/                saída da coleta, intocada; uma subpasta por fonte
│   ├── 02_intermediario/        bases empilhadas e limpas
│   └── 03_final/                painel UF × período usado nas estimações
├── docs/
│   ├── dicionario_siconfi.md    onde está cada variável nos anexos do RREO, RGF e DCA
│   ├── passo1_metodologia.md    método, medidas e limites do passo 1
│   ├── rreo_historico.md        como coletar e validar o RREO de 2000 a 2014
│   └── downloads_manuais.md     RREO e RGF de 2000 a 2014, CONFAZ, séries pré-2013, Base dos Dados
└── notebooks/
```

A regra é que `01_bruto` nunca é editado à mão. Toda limpeza sai de um programa em `scripts/` e grava em `02_intermediario` ou `03_final`, para que qualquer pessoa do grupo consiga refazer o caminho do dado bruto ao resultado.

## Como rodar

Com Python 3.10 ou mais recente:

```bash
pip install -r requirements.txt
python scripts/00_baixar_tudo.py
```

A coleta completa leva algumas horas, quase todas no RREO (27 estados, seis bimestres, sete anexos, de 2015 até hoje). Ela pode ser interrompida e retomada: arquivos já em disco são pulados. Cada fonte também roda isolada, por exemplo `python scripts/01_siconfi.py rgf --anos 2019 2024`. Tudo o que acontece fica registrado em `coleta.log`, na raiz.

Algumas bases não têm API aberta e entram por download manual, descrito em `docs/downloads_manuais.md`: o Boletim de Arrecadação do CONFAZ, as séries estaduais anteriores a 2013 (Execução Orçamentária de Estados e FINBRA histórico), caso a busca automática no Tesouro Transparente não as encontre, a versão compatibilizada do SICONFI na Base dos Dados e os RREOs e RGFs estaduais de 2000 a 2014, que só existem nos portais de cada secretaria.

## Qual base responde a qual pergunta

**(i) Pró-ciclicidade da poupança estadual.** A poupança corrente é a receita corrente menos a despesa corrente. Ela sai do RREO, Anexo 1 (bimestral, desde 2015), e da DCA (anual, desde 2013); antes disso, da Execução Orçamentária de Estados (1995-2013), do FINBRA histórico e do Ipeadata. O indicador 2 da CAPAG mede a mesma coisa em forma de razão e serve de checagem. O ciclo vem do PIB das Contas Regionais (anual), do IBCR do Banco Central (mensal, por estado ou região) e da desocupação da PNAD Contínua (trimestral). Com isso dá para estimar a correlação entre o componente cíclico da poupança e o hiato do produto estadual, em painel.

**(ii) Reação às crises recentes.** As datas de cada episódio estão em `dados/00_referencia/crises.csv`: 2008-09, 2014-16, 2020 e o corte de ICMS de 2022, que funciona como choque de receita sem recessão. Para cada estado, o RREO bimestral mostra o que se ajustou primeiro (investimento, custeio ou pessoal), o CONFAZ mostra a queda mensal do ICMS e as transferências do Tesouro mostram quanto a União compensou, inclusive pela LC 173/2020. A MSC mensal, a partir de 2018, mostra o uso do caixa durante a Covid.

**(iii) Endividamento, poupança e desempenho na crise.** As condições iniciais vêm do RGF (DCL/RCL, pessoal/RCL, disponibilidade de caixa), da CAPAG e do Boletim de Finanças dos Entes Subnacionais. O desempenho na crise pode ser medido por queda de investimento, atraso de restos a pagar (RREO, Anexo 7), garantias honradas pela União e adesão ao Regime de Recuperação Fiscal.

**Multiplicador fiscal estadual.** O caminho mais usado na literatura de painel regional é tratar variações de transferências federais com regra fixa de rateio, como o FPE, como choque de gasto que o estado não escolheu, e medir a resposta do PIB ou do IBCR. As transferências mensais por estado, desde 1997, estão na base B11 do catálogo.

**Colchão de liquidez e LRF.** O estoque de caixa e aplicações sai da DCA (balanço patrimonial, fim de ano), do RGF, Anexo 5 (disponibilidade líquida por vinculação) e da MSC (mensal). Os limites da LRF aparecem prontos no RGF. Os marcos legais que mudaram as regras ao longo do período estão em `dados/00_referencia/marcos_institucionais.csv`.

## Cuidados conhecidos

O plano de contas dos estados mudou em 2013 (MCASP) e o formato dos anexos do RREO e do RGF muda conforme cada edição do Manual de Demonstrativos Fiscais, então os rótulos de linha precisam de uma tabela de equivalência entre anos. O RREO traz valores acumulados no ano: o valor de cada bimestre é a diferença entre períodos consecutivos. No Manual de Análise Fiscal de 2025, usado pelo Tesouro na CAPAG, as transferências constitucionais dos estados aos municípios passaram a ser tratadas como dedução de receita, o que muda a comparação com os anos anteriores. Valores do SICONFI são declarados pelos próprios estados, e o Tesouro faz ajustes no PAF e na CAPAG; vale comparar as duas versões antes de fechar uma variável. Por fim, o PIB estadual tem cerca de dois anos de defasagem, o que torna o IBCR e a PNAD necessários para os anos recentes.
