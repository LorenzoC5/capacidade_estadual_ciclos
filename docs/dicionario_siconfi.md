# Dicionário SICONFI: de onde sai cada variável

A API devolve uma linha por célula do demonstrativo. As colunas que importam são `exercicio`, `periodo`, `uf`, `anexo`, `rotulo` (tabela dentro do anexo), `coluna` (por exemplo “Até o Bimestre”, “Previsão Atualizada”, “Despesas Liquidadas”), `cod_conta`, `conta` e `valor`. Para montar uma variável, filtra-se a conta e a coluna desejadas. Os rótulos de conta mudam entre edições do Manual de Demonstrativos Fiscais, por isso a tabela abaixo indica o anexo e a linha de referência, e a equivalência exata entre anos fica numa planilha de-para em `02_intermediario`.

| Variável do projeto | Relatório e anexo | Linha ou conta de referência | Coluna sugerida | Observação |
|---|---|---|---|---|
| Receita corrente | RREO, Anexo 01 | RECEITAS CORRENTES | Até o Bimestre (realizada) | Acumulada no ano |
| Despesa corrente | RREO, Anexo 01 | DESPESAS CORRENTES | Despesas liquidadas até o bimestre | Usar liquidada; empenhada infla o fim do ano |
| Poupança corrente | RREO, Anexo 01 | receita corrente menos despesa corrente | | Variável central da pergunta (i) |
| Investimento | RREO, Anexo 01 | INVESTIMENTOS (dentro de DESPESAS DE CAPITAL) | Liquidadas | Principal variável de ajuste nas crises |
| Pessoal e encargos | RREO, Anexo 01 | PESSOAL E ENCARGOS SOCIAIS | Liquidadas | |
| Juros e amortização | RREO, Anexo 01 | JUROS E ENCARGOS DA DÍVIDA; AMORTIZAÇÃO DA DÍVIDA | Liquidadas | Serviço da dívida |
| Despesa por função | RREO, Anexo 02 | funções (saúde, educação, segurança etc.) | Liquidadas | |
| Receita Corrente Líquida | RREO, Anexo 03 | RECEITA CORRENTE LÍQUIDA | Total dos últimos 12 meses | Denominador dos limites da LRF; traz os 12 meses separados |
| Previdência (RPPS) | RREO, Anexo 04 | receitas e despesas previdenciárias; resultado | Até o Bimestre | Peso crescente nas despesas obrigatórias |
| Resultado primário | RREO, Anexo 06 | RESULTADO PRIMÁRIO | Até o Bimestre | Acima da linha; comparar com BCB abaixo da linha |
| Restos a pagar | RREO, Anexo 07 | restos a pagar processados e não processados | Saldo | Atraso de pagamento em crise |
| Regra de ouro | RREO, Anexo 09 | operações de crédito e despesas de capital | | |
| Despesa com pessoal / RCL | RGF, Anexo 01 | DESPESA TOTAL COM PESSOAL; % sobre a RCL | | Limites da LRF por poder |
| Dívida Consolidada Líquida | RGF, Anexo 02 | DÍVIDA CONSOLIDADA LÍQUIDA; % DCL sobre RCL | Saldo do quadrimestre | Limite de duas vezes a RCL para estados |
| Garantias | RGF, Anexo 03 | total das garantias concedidas | | |
| Operações de crédito | RGF, Anexo 04 | operações de crédito contratadas | | |
| Disponibilidade de caixa | RGF, Anexo 05 | disponibilidade de caixa líquida por vinculação | | Só no 3º quadrimestre; medida do colchão |
| Caixa e equivalentes (fim do ano) | DCA, Anexo I-AB | Caixa e Equivalentes de Caixa; Investimentos e Aplicações Temporárias | | Estoque de liquidez |
| Ativo e passivo financeiro | DCA, Anexo I-AB | quadro de ativos e passivos financeiros | | Superávit financeiro |
| ICMS, FPE e outras receitas | DCA, Anexo I-C | contas de natureza de receita | Receitas realizadas | Separa receita própria de transferência |
| Despesa por natureza | DCA, Anexo I-D | elementos de despesa | Liquidadas | |
| Caixa mensal | MSC patrimonial, classe 1 | contas de caixa e equivalentes (1.1.1) | ending_balance | A partir de 2018; permite separar fontes livres e vinculadas |

Dois avisos práticos. Primeiro, o RREO do 6º bimestre e a DCA do mesmo ano nem sempre batem, porque a DCA é fechada depois e com outro recorte; para séries anuais, a DCA é a referência e o RREO serve para a dinâmica dentro do ano. Segundo, o SICONFI aceita retificações: rodar a coleta de novo meses depois pode trazer valores diferentes para períodos antigos, então convém guardar a data da coleta junto com cada versão do painel.
