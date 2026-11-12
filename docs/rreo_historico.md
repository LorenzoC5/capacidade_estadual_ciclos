# RREO de 2000 a 2014: coleta nos portais estaduais

A API do Siconfi só tem o RREO dos estados a partir de 2015. Os relatórios de 2000 a 2014 existem, mas estão espalhados pelos portais de cada estado, quase sempre em PDF. Este guia descreve como transformá-los numa série contínua com a API.

## O fluxo

O trabalho tem três etapas, cada uma com uma rotina.

`40_rreo_baixar.py` lê a URL de cada estado em `dados/00_referencia/rreo_portais.csv`, percorre a página, segue os links que parecem levar a relatórios da LRF e baixa os arquivos que parecem ser RREO, identificando ano e bimestre pelo texto do link. Tudo o que encontrou fica em `_manifesto.csv`, na pasta do estado, inclusive o que não baixou e por quê.

Na prática, a maioria dos portais não se deixa percorrer assim: páginas montadas por JavaScript, buscas por formulário, sites antigos que saíram do ar. Para esses estados o catálogo usa o tipo `lista`, e os endereços de cada relatório ficam em `dados/00_referencia/rreo_links/<UF>.csv` (colunas `ano`, `bimestre`, `parte`, `url`, `membro`, `observacao`). A rotina só baixa o que está na lista e confere se o arquivo é mesmo um PDF. Quando o estado publica um arquivo por anexo, a coluna `parte` distingue os pedaços (`anexo01`, `anexo03` etc.) e o nome do arquivo ganha esse sufixo. Quando o estado só publica um ZIP com vários relatórios, `url` aponta para o ZIP e `membro` diz qual arquivo tirar dele (ZIPs dentro de ZIPs separados por `/`). Muitos links dos primeiros anos apontam para o Wayback Machine, no formato `https://web.archive.org/web/<data>id_/<endereço original>`, que devolve o arquivo como foi guardado; a lista de tudo o que o Wayback guardou de um domínio sai da API CDX (`http://web.archive.org/cdx/search/cdx?url=<domínio>/*&filter=mimetype:application/pdf`).

`41_rreo_extrair.py` abre cada arquivo, localiza o Balanço Orçamentário e o demonstrativo da RCL e lê as linhas principais: receita corrente, receita tributária, transferências correntes, receita de capital, operações de crédito, despesa corrente, pessoal, juros, outras despesas correntes, despesa de capital, investimentos, inversões e amortização. Para escolher a coluna certa, usa a identidade contábil da própria linha (previsão atualizada igual a realizado mais saldo, na receita; dotação atualizada igual a liquidado mais saldo, na despesa). Assim a rotina não depende da posição exata das colunas, que muda entre estados e anos. Quando a identidade não fecha, usa a posição padrão e marca a linha.

`42_rreo_serie_continua.py` junta os PDFs (até 2014) com a API (de 2015 em diante), calcula o fluxo de cada bimestre e roda as checagens de qualidade.

## Ordem de trabalho recomendada

Os 27 estados já estão no catálogo, todos com o tipo `lista`; a coluna `observacao` resume a cobertura e as lacunas de cada um. Para baixar tudo de novo, basta `python scripts/40_rreo_baixar.py --todos`. Alguns servidores (o da SEFAZ-AC, por exemplo) não enviam o certificado intermediário da cadeia; a rotina confia nos certificados padrão do `certifi` mais os intermediários públicos guardados em `dados/00_referencia/certificados/`, o que resolve sem desligar a verificação. O Wayback Machine limita requisições em sequência, então pode ser preciso rodar a rotina mais de uma vez até todos os arquivos virem (o que já está em disco é pulado).

O que ficou de fora, e por quê:

- Amapá não tem nenhum RREO de 2000 a 2015 em PDF ou planilha; só páginas HTML de 2000 a 2004 no Wayback.
- Mato Grosso do Sul de 2000 a 2002 só existe em HTML, que a rotina não lê. Os ZIPs do Maranhão (2001 a 2012), do Piauí (2001 e 2002) e do Distrito Federal (2002 e 2003) já entram pela coluna `membro`, com duas exceções: o ZIP de 2008 do Maranhão e o de 2001 do Piauí estão corrompidos.
- Rio Grande do Norte só tem 2010 em diante, e Roraima só 2012 em diante.
- Parte dos arquivos é escaneada ou tem as tabelas como imagem (Amazonas, Mato Grosso de 2002 a 2006, Mato Grosso do Sul até 2006, Santa Catarina em 2003, Rondônia de 2001 a 2005) e precisa de OCR.

Para um estado novo, ou para refazer a lista de um deles, a sequência é a mesma que serviu para Mato Grosso:

1. montar `dados/00_referencia/rreo_links/MT.csv` com um link por bimestre (ou por anexo), conferindo o período impresso em cada arquivo, porque vários portais trocam bimestres; se o portal for uma página simples, o tipo `pagina` com `--listar` pode poupar esse trabalho;
2. baixar os arquivos (`--uf MT`, sem `--listar`) e abrir alguns no visualizador para ver se são texto ou imagem;
3. testar a extração em um arquivo de cada fase do leiaute (por exemplo 2002, 2006, 2010, 2014), com `--arquivo ... --mostrar`, e conferir os números com o PDF aberto;
4. extrair o estado inteiro e rodar a rotina 42.

Para cada estado novo, o passo 1 é o que mais muda. Os passos seguintes costumam funcionar sem ajuste, a não ser nos primeiros anos da LRF.

## Validação

Baixe também o RREO de 2015 de cada estado, em PDF. Como 2015 também existe na API, a rotina 42 compara as duas versões, variável por variável, e emite alerta para diferenças acima de 1%. Esse é o teste mais confiável de que a extração está certa para aquele estado e aquele leiaute.

A rotina também acusa acumulados que caem ao longo do ano, o que costuma indicar coluna errada ou relatório retificado, e anos com bimestres faltando. Para os valores anuais, vale ainda comparar o 6º bimestre com a série anual da Execução Orçamentária de Estados, do Tesouro, quando ela estiver na pasta.

## Problemas esperados

Os primeiros anos (2000 a 2004) seguem leiautes anteriores ao Manual de Demonstrativos Fiscais, e alguns estados só publicavam no diário oficial. Nesses casos, pode ser mais rápido digitar as poucas linhas de interesse do 6º bimestre do que adaptar a extração.

PDFs escaneados não têm texto. A rotina 41 marca esses arquivos como `sem_texto`. Para eles, rodar OCR antes (por exemplo, `ocrmypdf --language por arquivo.pdf arquivo.pdf`) e extrair de novo; números lidos por OCR precisam de conferência manual.

Alguns relatórios vêm em milhares de reais. A rotina detecta a unidade pelo cabeçalho, mas vale conferir os primeiros resultados de cada estado.

Os rótulos mudaram ao longo do tempo: “Receita Tributária” virou “Impostos, Taxas e Contribuições de Melhoria”, por exemplo. As expressões usadas para cada variável estão no topo de `41_rreo_extrair.py` e podem ser ampliadas.
