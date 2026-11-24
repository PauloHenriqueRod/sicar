# Extração de documentos de RH por página

O [fluxo de anexos opcionais e revisão](fluxo-revisao-calculos.md) descreve a situação por arquivo, a resolução explícita de conflitos, o histórico das fontes substituídas e o uso das entradas finais pela API/motor.

A extração oferece observações editáveis para conferência manual do RH. Ela não reconhece direito, quitação, gozo de férias nem autenticidade documental.

## Leitores por layout — versão 5

`app/services/leitores_pdf/registro.py` seleciona o leitor pelo conteúdo, página e seção. O worker conserva texto original e posições de palavras; cada leitor reconstrói apenas as colunas do seu layout. `extracao_documentos.py` é a fachada compatível. O núcleo financeiro e as conversões delimitadas são compartilhados pelos perfis equivalentes, sem criar um parser por pessoa ou nome de arquivo.

| Identificador | Cobertura |
|---|---|
| `siape_tae`, `siape_docente`, `siape_substituto` | Fichas com cargo/código reconhecido, rubricas mensais e posição observada por página. |
| `siape_cd`, `siape_fg` | Variações com função explicitamente preenchida; compartilham as colunas financeiras SIAPE. |
| `siape_financeira` | Estrutura financeira reconhecida com carreira ainda não identificada; não assume enquadramento. |
| `cadastro_siapecad_colunas` | Cadastro com cabeçalhos e valores em linhas distintas, matrícula/nome/regime, cargo/emprego, exercício compacto e jornada. |
| `cadastro_rotulado` | Formato rotulado delimitado anterior, preservado por compatibilidade. |
| `cacoferias_formulario` | Formulário com parcelas, datas, quantidade, cancelamento, interrupção, reinício, saldo e continuação explícitos. |
| `cacoferias_tabular` | Formato INICIO/DIAS/PARCELA e sua continuidade comprovada. |
| `portaria_docente_progressao`, `portaria_docente_titulacao`, `portaria_tae_anexo`, `ato_substituicao` | Dispositivos e anexos analisados, com seleção própria e separação de papéis/datas. |

Regiões com mais de um layout candidato não são entregues arbitrariamente ao primeiro leitor. Páginas desconhecidas ficam sem interpretação genérica, inclusive quando contêm rótulos como cargo/nome. PDFs mistos conservam origens e pendências distintas. Continuidade de tabela exige geometria/contexto compatíveis; não se herda natureza entre páginas nem entre cabeçalhos. Nos perfis SIAPE identificados, `natureza_origem` distingue `EXPLICITA` e `GRUPO`, encerrando o grupo em mudanças de bloco, exercício, cabeçalho ou totais. Tabela genérica sem identificação SIAPE não recebe essa herança.

As ocorrências conservam `descricao_rubrica`; IQ explicitamente descrito produz um campo de percentual com a mesma competência. Cargo e posição não são tratados como uma única situação válida por todo o documento: cada página conserva o observado. Classificação TAE é separada de códigos de classe/nível docente; códigos históricos não são convertidos em denominações de carreira sem referência confirmada. Função vazia não recebe os rótulos vizinhos. T. serv. vazio permanece ausente.

Uma razão adicional/VB só é sugerida quando há uma ocorrência positiva e identificada de cada componente na mesma página/bloco/competência e sequência regular. A sugestão fica `AMBIGUO`, `sugestao=true`, com `fontes_campo_ids`; não confirma integralidade, base, concessão ou regra. Complementos/duplicidades impedem essa sugestão. Rubrica 750 não comprova quitação; 98002/98004 não comprovam direito ao abono.

No CACOFERIAS, `parcela`, `cancelada`, `continuacao`, `data_interrupcao`, `reinicio` e `dias_restantes` conservam a situação observada. Interrupção/continuação ou situação não identificada exigem escolha explícita do fim e revisão da aplicabilidade. A ação de adicionar uma parcela cancelada fica desabilitada; preenchimento manual justificado continua disponível. Fim calculado e informado permanecem separados.

Ata ainda não tem leitor: a seção de upload é opcional e informa o limite. O exemplo adicional analisado identifica-se como portaria, cuja redação RETROATIVA foi incorporada. Imagem sem texto não recebe OCR implícito. Tabelas remuneratórias são importadas no cadastro, conforme [os adaptadores de fontes](importacao-fontes-oficiais.md), sem upload obrigatório por cálculo.

### Metadados e aplicação

O upload aceita `metadados_arquivos`, JSON opcional com um `{id, categoria}` por arquivo, na mesma ordem de `arquivos`. IDs são únicos no envio; categorias são as seções do formulário. Resultados/falhas retornam `indice_arquivo` e, quando informado, `arquivo_id`. Assim, arquivos com o mesmo nome não trocam de categoria. `categoria_informada` é expectativa do operador, não evidência de conteúdo; divergência gera aviso sem forçar outro leitor.

`leitores` registra identificador, versão e páginas; cada campo conserva seu leitor quando disponível. Novos metadados vazios são omitidos na serialização para preservar a comparação das entradas de snapshots anteriores. Reenvio do mesmo conteúdo e conjunto de versões não duplica fontes; leitor atualizado gera proposta separada, sem aplicar pagamentos ou substituir edições automaticamente.

Os filtros de revisão preservam a origem dos campos. Frontend e API validam os destinos de identificação, exercício, jornada e percentuais. `test_leitores_pdf.py` cobre perfis, geometria, metadados, limites e versões.

## Contrato e compatibilidade

`POST /api/extrair-pdf`, autenticado, continua recebendo `tipo_calculo` e até 10 PDFs em `arquivos`. O parâmetro `versao_extracao=2` ativa o contrato comum; omitido, mantém o retorno legado. O frontend atual solicita a versão 2. `GET /api/calculos/contratos/extracao` publica os esquemas do documento e da revisão. Os contratos de cálculo aceitam `dados_extraidos.revisao_extracao` opcional, sem reescrever históricos anteriores.

Na versão 2, `resultados` contém arquivos processados com `filename`, `dados_extraidos` (reservado à compatibilidade) e `extracao`. `falhas` identifica cada arquivo rejeitado por nome, código e mensagem segura. `resumo` informa recebidos, interpretados e falhas. Falhas individuais retornam diagnóstico no lote, inclusive quando todos falham, para permitir preenchimento manual. Autenticação e limites globais da requisição continuam sendo erros da requisição inteira.

Cada documento tem ID, nome, impressão SHA-256 do conteúdo, layout, versão do leitor, situação, quantidade de páginas, blocos de identificação, campos e avisos. A impressão serve apenas para reconhecer reenvios dentro da revisão do usuário; não há cadastro global de documentos ou armazenamento permanente do PDF. A situação distingue `CONCLUIDO`, `PARCIAL`, `SEM_TEXTO` e `NAO_SUPORTADO`.

O envelope atual é `rh_paginas_v5`; snapshots de `rh_paginas_v1`, `rh_paginas_v2`, `rh_paginas_v3` e `rh_paginas_v4` continuam aceitos. Cada leitor também possui identificador e versão próprios. Os [atos e portarias opcionais em formatos delimitados](extracao-atos-portarias.md) preservam papéis, datas e destinos sem aplicar regras do direito. A versão do leitor é distinta da versão 2 do protocolo da API. Reprocessar o mesmo arquivo com leitor atualizado apresenta outra fonte para revisão, sem substituir silenciosamente as evidências ou edições anteriores.

Cada campo preserva ID, bloco, nome do campo, valor normalizado textual, texto observado limitado, estado, página e localizador. Uma ocorrência financeira também conserva competência, rubrica, natureza e sequência; um período conserva início e fim. Valores monetários não passam por float no novo leitor. Colunas TOTAL não são pagamentos. Ocorrências repetidas permanecem como evidências independentes para a conciliação financeira posterior.

Estados: `EXTRAIDO`, `AUSENTE`, `AMBIGUO` e `ILEGIVEL`. Ausência mantém valor/página nulos e registra as páginas analisadas, sem inventar página de origem. Campos singulares divergentes no mesmo bloco preservam os candidatos e ficam ambíguos. Não há preenchimento automático com zero; `0,00` explícito é preservado.

## Layouts delimitados suportados

| Layout | Reconhecimento e campos | Limites da interpretação |
| --- | --- | --- |
| Ficha SIAPE — TAE/docente/substituto | Ano `referente a`, cabeçalho `Nome: matrícula - nome`, `Cargo/Lotação`, `Função/Exerc.`, `T. serv.`, rubricas de cinco dígitos e colunas mensais, natureza e sequência | Categoria somente quando descrita no texto. Posição permanece texto observado; não se aplica uma classificação TAE a docente nem se infere posição pelo salário. |
| Cadastro funcional | Nome/matrícula rotulados, vínculo/contrato explícitos, seção `CARGO/EMPREGO`, `Cargo:` e `EXERCICIO` com data | Entrada em exercício só é lida dentro da seção, encerrada por seções reconhecidas ou pela mudança de página. Outras datas chamadas exercício não viram início do contrato. |
| CACOFERIAS | Colunas INICIO, DIAS e PARCELA; opcionalmente FIM, matrícula, nome, vínculo e exercício; datas DD/MM/AAAA ou DDMMMYYYY | Mantém parcelas separadas e compara o fim explícito com o fim inclusivo calculado pelos dias. Programação não comprova gozo, pagamento ou interrupção aplicável. |

O worker lê texto por página e usa posições de palavras para reconstruir as colunas dos cabeçalhos reconhecidos, inclusive sem caracteres `|`. Tabelas delimitadas por `|` continuam suportadas. Cabeçalhos repetidos não criam concessões novas. A continuidade conserva contexto do bloco; identificação diferente inicia outro bloco. Rótulos explícitos de responsável pela emissão não são usados como servidor. Formatos não reconhecidos permanecem manuais. Não há OCR nem promessa de interpretação genérica de qualquer PDF de RH.

Na versão 4, o cabeçalho da tabela de rubricas também encerra o bloco de identificação do emissor. Assim, fichas com o responsável pela emissão antes da tabela conservam os valores financeiros sem atribuir ao servidor a identidade do emissor. Natureza R/D sem contexto comprovado permanece nula e marcada como ambígua. Na v5, a coluna agrupada dos perfis SIAPE analisados pode fornecer a natureza às linhas seguintes, com origem GRUPO; o código da rubrica não determina R/D. A interface mostra uma contagem dos valores e das ocorrências financeiras observadas, com orientação para abrir os dados e associar pessoa/vínculo antes de aplicar as entradas. Regressões usam PDF docente sintético pelo endpoint de progressão e o worker real, além de verificar a preservação das versões anteriores.

A geometria de tabelas financeiras e de programação de férias pode continuar na página seguinte sem repetir o cabeçalho quando o contexto for compatível. Para fichas, são conferidos largura, identificação, vínculo e exercício observados; os dados do emissor não são considerados como identidade do servidor. Sem continuidade financeira comprovada, as ocorrências reconhecíveis são preservadas sem competência presumida e o documento fica parcial. O leitor compara as atribuições por posição do cabeçalho e por centro do valor; se alinhamento à direita ou outra disposição admitir competências diferentes, preserva o valor, deixa a competência nula e marca `AMBIGUO`, sem deslocá-lo para outro mês nem descartá-lo como TOTAL. Os limites do worker não foram aumentados.

Uma identificação encontrada depois de ocorrências sem pessoa comprovada não identifica retroativamente essas ocorrências. Elas permanecem em bloco separado para associação manual; o documento informa a pendência. Nome/matrícula e vínculo encontrados antes dos fatos continuam compondo normalmente o cabeçalho do bloco.

Nos períodos de férias, `dias_informados`, `fim_informado` e `fim_calculado` mantêm os dados e candidatos. Quando há divergência ou fim informado ilegível, `fim` permanece nulo e o estado é ambíguo/ilegível. A revisão exibe os candidatos e exige escolha explícita antes de adicionar o período à substituição; não transforma o fim calculado em informação documental. Correções posteriores continuam permitidas com justificativa.

As rubricas **00750** e **98002** conservam ocorrências, valores, sinais, naturezas, sequências e competências. A presença da 750 não confirma qual período foi quitado; a presença da 98002 não confirma direito ao abono. A aplicação na revisão cria lançamentos sem presumir papel, categoria, operação, folha ou concessão. Os motores existentes exigem os vínculos, regras e confirmações pertinentes.

## Associação, revisão e aplicação

Sem arquivos, o RH segue para o [preenchimento manual](fluxo-revisao-calculos.md).

Os documentos são apresentados no processo com blocos separados. Cada bloco exige associação explícita a servidor ou titular (somente substituição), matrícula e vínculo, ou descarte justificado. Matrícula incompatível e vínculo explicitamente diferente não podem ser unidos; o operador deve desconsiderar o bloco e usar a fonte correta. Identificação ausente exige justificativa da associação manual. Nome isolado nunca confirma identidade. O vínculo da revisão precisa corresponder ao vínculo/contrato do plano financeiro quando este o identifica.

Os campos podem ser aplicados explicitamente a destinos do formulário, sem sobrescrever valores já editados. Rubricas podem ser adicionadas aos lançamentos de revisão, preservando a origem. A programação de férias pode alimentar períodos de substituição apenas por ação explícita, mantendo motivo/aplicabilidade para conferência. Dados de titular não podem preencher os campos do substituto e vice-versa.

`aplicacoes` registra documento/campo, destino, valor revisado, justificativa e identificação da linha financeira quando existente. Edição ou resolução de ambiguidade exige justificativa; simples normalização monetária não caracteriza alteração de valor. Reordenar/remover linhas preserva as origens pela identidade da linha, sem atribuí-las à linha seguinte. A API confere se o valor final corresponde à revisão registrada, rejeita destinos reservados e impede aplicações de blocos descartados ou não associados.

Edições invalidam as confirmações afetadas. Reenvios preservam campos e associações. Conteúdo e versão idênticos não duplicam fontes. Mesmo nome com conteúdo diferente exige nova decisão. O limite é de dez fontes por revisão. Falhas individuais permitem reenvio. O [histórico](memoria-calculos.md) guarda a evidência utilizada no cálculo e o processamento remove os PDFs temporários.

## Limites, testes e homologação

Por PDF, o worker admite 5 MiB, 100 páginas, um milhão de caracteres, 512 MiB e 15 segundos, com dois leitores simultâneos por processo da API. Excedentes geram aviso de extração parcial. Os perfis financeiros e CACOFERIAS tabular (leitor v2) preservam a geometria nas continuações e incluem posições derivadas no limite de campos.

`test_extracao_documentos.py` cobre colunas, continuação de páginas, identificação tardia, períodos e falhas parciais. `documentExtraction.test.ts`, `ExtractionReview.test.tsx` e `App.extraction.test.tsx` verificam associação, aplicação e reenvio. O RH confere o documento e a aplicabilidade ao vínculo.
