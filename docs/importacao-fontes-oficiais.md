# Importação de fontes oficiais no cadastro

Depende do cadastro por vigência da issue #18. A importação cria uma **prévia persistida**, nunca ativa valores durante a leitura. O RH confere a autenticidade do documento, o enquadramento, os efeitos financeiros e o direito. Nenhum arquivo real do RH ou documento local de análise integra esta entrega. Não há cadastro de nome, matrícula ou outros dados pessoais nesses registros públicos; colunas externas ao mapeamento não são persistidas.

## Fontes e escopo

- [Cadernos históricos MGI, desde 1998](https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/tabela-de-remuneracao-dos-servidores-publicos-federais-civis-e-dos-ex-territorios-1): VB, RT e tabelas de cargos/funções, conforme cada edição.
- [Anexos oficiais de VB e RT da Lei 13.325/2016](https://www.presidencia.gov.br/ccivil_03/_ato2015-2018/2016/lei/anexo/anl13325-i-iv.htm): incluem efeitos anteriores a 2020; a fonte e o intervalo aplicável precisam ser conferidos.

Os links foram consultados em 26/10/2026. A aplicação não baixa URLs nem afirma autenticidade com base no domínio: a URL HTTPS oficial (gov.br, edu.br ou ufpi.br e seus subdomínios) é metadado de proveniência, conferido pelo operador. Prefira um arquivo estruturado equivalente ao PDF. Esta entrega não inclui valores oficiais previamente homologados nem certifica a cobertura de todas as carreiras/posições desde 2020.

As tabelas pertencem à gestão cadastral. Não há novo upload obrigatório na execução de um cálculo. Componentes de CD/FG/FCC são cadastrados separadamente; sua escolha, combinação remuneratória e direito não são presumidos nem aplicados automaticamente à substituição.

## Leitura suportada

Os adaptadores em `leitores_pdf/tabelas.py` executam no worker de PDF (5 MiB por arquivo, 100 páginas, 15 segundos e 512 MiB). O processamento remove os temporários.

- **Anexos TAE:** IQ com efeitos expressos, VB por classificação e padrão, e situação anterior por capacitação quando as colunas I–IV estiverem comprovadas pela geometria. Correspondências originais ficam na evidência. O cabeçalho cortado de abril não comprova o ano; a vigência dessa coluna fica pendente, sem usar o nome do arquivo para completá-la.
- **Comparativo TAE 2025/2026:** VB por classificação/padrão e colunas de janeiro/2025 e abril/2026, somente com efeitos identificados no cabeçalho. Percentuais de IQ sem vigência expressa permanecem pendentes.
- **Comparativo do magistério:** seis colunas de VB, separadas em 20h, 40h e DE. Abril/2026 possui início reconhecível; a coluna “até março/2026” informa fim, mas não comprova início. Não contém RT e não a gera.

Campos não informados, como vínculo, jornada TAE ou versão histórica, continuam ausentes. A prévia exige revisão desses dados antes da ativação. Em configuração opcional de leitura, `aba=PDF` permite contexto manual para campos ausentes; dados efetivamente observados não são sobrescritos. Página, linha, leitor/versão, texto delimitado e contexto fornecido são preservados em `original`. Formato desconhecido retorna rejeição revisável; PDF inválido é rejeitado sem expor detalhes internos. O cálculo individual continua sem precisar anexar tabelas.

IQ usa `EstruturaIQ` e `ReferenciaIQ`, com percentual `Numeric(30,12)`, titulação, vigência, origem e revisão. Sua ativação é independente de VB/RT e não concede direito individual nem altera o percentual revisado de um cálculo. Duplicidades, divergências e sobreposições são verificadas; a cobertura pode ser consultada por `tipo=IQ`. As origens/revisões de IQ permanecem nas linhas do lote e na fonte da referência; o endpoint antigo de origens por ID de VB/função conserva seu escopo.

### Migração e recuperação dos percentuais de IQ

`migrate_official_sources` acrescenta apenas `estrutura_iq` e `referencia_iq`, de forma repetível, sem alterar colunas ou valores das tabelas anteriores. Antes de implantar, fazer backup recuperável e executar a migração em banco temporário. Rollback da aplicação preserva as tabelas novas e a prévia/histórico; não apagar registros para reverter a interface. PostgreSQL aplica exclusão de vigências concorrentes; SQLite usa gatilhos equivalentes para os testes locais. O teste de integração PostgreSQL foi ampliado para IQ e deve rodar no CI com `TEST_POSTGRES_URL` de banco exclusivo de teste.

### Arquivos e colunas

CSV UTF-8 (vírgula ou ponto e vírgula), XLSX, ODS e os três PDFs descritos acima aceitam registros `VB`, `RT`, `IQ` ou `FUNCAO` conforme o layout. IQ exige percentual, escolaridade/titulação e vigência. Colunas canônicas:

```text
tipo;carreira;vinculo;jornada;versao_carreira;classificacao_tae;capacitacao_tae;padrao_tae;classe_docente;nivel_docente;inicio_vigencia;fim_vigencia;valor;titulacao;tipo_funcao;codigo_funcao;modalidade;componente
```

São reconhecidas diferenças de acentos, caixa e separadores nos cabeçalhos. `regime`, `vigencia inicial`, `vigencia final` e `valor R$` têm aliases explícitos. Cabeçalhos repetidos não viram valores; colunas duplicadas geram rejeição. Linhas sem cabeçalho ou sem campos obrigatórios permanecem rejeitadas. Não há preenchimento vertical de classe, jornada ou data a partir de linhas anteriores.

Em uma regra explícita, todas as colunas mapeadas precisam existir no cabeçalho, inclusive campos opcionais como `fim_vigencia`. Um cabeçalho incompleto gera rejeição e invalida o mapeamento anterior daquele bloco até que apareça outro completo. Assim, uma coluna de término não reconhecida não vira vigência aberta. Uma célula de término vazia sob um cabeçalho completo continua permitindo fim em aberto, sujeito à conferência do RH.

A detecção inclui cabeçalhos parciais sem a coluna de valor, evitando reutilizar posições de VB/RT de um bloco anterior. Um rótulo isolado também é considerado indício de cabeçalho quando a coluna de valor anterior não contém um número. Dados legítimos que coincidem com um único rótulo e mantêm valor numérico continuam sendo lidos; cabeçalhos e contextos precisam ser conferidos pelo operador.

No ODS, o leitor percorre `table-header-rows`, `table-rows` e `table-row-group`, incluindo grupos aninhados, na ordem do documento. As repetições de linhas, inclusive vazias, preservam a localização e continuam sujeitas aos limites de leitura. A estrutura desses contêineres é descrita na [especificação OASIS OpenDocument 1.3, Parte 3, seções 9.1.7–9.1.9](https://docs.oasis-open.org/office/OpenDocument/v1.3/os/part3-schema/OpenDocument-v1.3-os-part3-schema.pdf), consultada em 27/10/2026.

Repetições de células vazias preservam a posição das colunas. A cauda vazia de uma linha pode ultrapassar 64 colunas sem ser expandida em memória, mas qualquer valor posterior continua na posição original e é rejeitado se estiver além desse limite; ele nunca é deslocado para uma coluna anterior.

Valores monetários são mantidos como textos decimais, validados como Decimal e persistidos em Numeric(30,12). Separadores brasileiros completos, como `1.234,56`, são normalizados sem arredondamento. Não use pontos de milhar sem separador decimal: `1.234` significa decimal com ponto. Consulte e corrija esse dado na prévia quando o layout for ambíguo.

Datas de efeitos são obrigatórias e independem de `publicado_em`. São aceitas datas ISO, datas completas brasileiras na leitura e células XLSX reconhecidas como data pelo formato da célula. Um ano ou número sem formatação de data não vira início de vigência. Não há corte em 01/01/2020: referências anteriores, como uma vigente desde 2019, podem cobrir o início do escopo.

Tabelas largas podem usar `leituras`: uma regra por aba, bloco de linhas e coluna de valor, com mapeamento explícito de cabeçalhos e contexto fixo conferido. Exemplo sintético:

```json
{
  "aba": "Docentes",
  "colunas": {"valor": "VB 20 horas", "classe_docente": "Classe", "nivel_docente": "Nível", "inicio_vigencia": "Efeitos"},
  "contexto": {"tipo": "VB", "carreira": "MAGISTERIO_SUPERIOR", "vinculo": "EFETIVO", "jornada": "20H", "versao_carreira": "estrutura-sintetica"}
}
```

Uma leitura distinta deve mapear 40h ou DE. Para blocos diferentes na mesma aba, use `linha_inicial` e `linha_final`, incluindo o cabeçalho de cada bloco; assim o contexto de um bloco não se aplica ao seguinte. Se a jornada/vigência varia nas linhas, mapeie a coluna respectiva em vez de fixar um contexto. Não se pode mapear uma coluna e um valor fixo para o mesmo campo. Abas sem regra explícita são informadas para revisão, sem reutilizar o contexto de outra aba. O operador continua responsável por conferir os dados de cada prévia: não existe interpretação universal dos layouts dos cadernos MGI.

Imagens, XLS, documentos protegidos e PDFs fora dos layouts suportados permitem cadastro manual validado, com página ou aba. Uma linha rejeitada exige correção e revisão salva antes da ativação.

Limites: 5 MB por arquivo, ZIP expandido até 20 MB/1000 entradas, até 30 abas, 2000 linhas/registros e 64 colunas. Há também limite de 5 MB de texto lógico/projetado, inclusive após repetição de linhas ODS, e dois leitores simultâneos por processo. Células excessivas, fórmulas e valores de erro não são executados nem considerados resultados de cálculo. XML usa defusedxml. Links externos, macros e arquivos embutidos não são executados/baixados. O arquivo é fechado após a leitura; o cadastro guarda metadados, hash e valores lidos/revisados, sem manter o binário. No cadastro manual, o hash identifica o conteúdo e os metadados digitados, não o arquivo oficial que não foi enviado.

## Fluxo e ativação

1. Informar identificação/edição, URL oficial, data de obtenção e, opcionalmente, publicação.
2. Enviar fonte estruturada ou preencher registros manuais. Para cadastrar VB e RT juntos, adicione os dois registros à mesma prévia manual antes de gerá-la. A prévia mostra valores, posição, jornada, efeitos e localização de cada linha.
3. Corrigir campos ou localização; a versão da linha aumenta. O dado original e sua localização original permanecem preservados.
4. Selecionar todas as linhas da mesma posição/vigência e confirmar a conferência do RH.
5. Verificar o resultado e o relatório de rejeições/conflitos, disponível também em JSON.

Estados: `PENDENTE`, `REJEITADA`, `CONFLITO`, `ATIVADA`, `DUPLICADA`. Revisões já ativadas/duplicadas são imutáveis. Requisição com uma versão anterior retorna 409 para impedir ativar uma prévia que mudou após a conferência.

VB e RT somente são agrupados se coincidirem carreira, vínculo, jornada, versão histórica, posição e intervalo inclusivo. Uma nova referência exige VB; RT isolada sem VB confirmado compatível não presume salário. RT isolada que já corresponde exatamente a uma referência confirmada é duplicidade. Quando há VB confirmado da mesma posição e intervalo exato, a ativação conferida pode acrescentar apenas titulações de RT ausentes, até 20 por referência. Não modifica VB, vigência, fonte do VB ou RT já cadastrada. Valores divergentes continuam em conflito. Cada RT acrescentada mantém a origem e a revisão na linha/lote que a introduziu; a fonte do cabeçalho salarial identifica o VB, e as fontes de RT são rastreadas pelos registros vinculados ao mesmo ID de referência e titulação. TAE não recebe RT docente; IQ continua sendo parâmetro separado do cálculo.

Funções usam identidade própria: `tipo_funcao` (CD/FG/FCC), `codigo_funcao`, `modalidade` e `componente`. O valor de vencimento de CD, representação, gratificação e total eventualmente informado na fonte são componentes distintos, sem soma automática. Modalidade/opção precisa ser explícita. Cada componente tem suas próprias datas e valor Numeric.

Vigências sobrepostas na mesma seleção são rejeitadas antes da ativação, inclusive entre grupos com datas diferentes. Referências confirmadas nunca são sobrescritas. Uma equivalência exata retorna `DUPLICADA`; valores/intervalos incompatíveis retornam `CONFLITO`. Falha de um grupo não promove esse grupo; grupos independentes válidos podem ser ativados, com relatório por linha. Restrições únicas e exclusões no PostgreSQL/triggers no SQLite cobrem também conflitos de escrita. Não se deve considerar SQLite uma validação da concorrência PostgreSQL.

## Contratos HTTP

Todos os endpoints usam sessão e exigem admin/dev, com auditoria de prévia, revisão e ativação. Prefixo `/api/tabelas/fontes`:

| Método e caminho | Contrato |
| --- | --- |
| `GET /catalogo` | Links, formatos e nota de conferência. |
| `POST /previa` | Multipart: `arquivo` e `metadados` JSON (`ConfiguracaoFonte`). Retorna prévia e rejeições; não ativa. |
| `POST /manual` | `origem`, lista `linhas` e `localizador`. Cria prévia manual, sujeita às mesmas validações. |
| `GET ?pagina=1` | Histórico de prévias salvas, 20 por página. |
| `GET /{lote_id}` | Origem, obtenção, publicação, arquivo, SHA-256, linhas, estados e rejeições. |
| `PUT /{lote_id}/linhas/{linha_id}` | `versao`, `dados`, `localizador`; preserva o original e valida os novos dados. |
| `POST /{lote_id}/ativar` | `linhas: [{id, versao}]` e `conferido_pelo_rh: true`; retorna resultados por linha. |
| `GET /origens?referencia_id=1&tipo=SALARIO&pagina=1` | Histórico das fontes de VB/RT ou `FUNCAO`, com obtenção, publicação, localização, revisão e valor conferido. |
| `GET /funcoes?pagina=1` | Componentes confirmados de CD/FG/FCC, com valores decimais em texto. |
| `GET /cobertura?inicio=2020-01-01&fim=2026-12-31&tipo=SALARIO&pagina=1` | Cobertura de VB/RT ou `FUNCAO`, por estrutura e componente. |
| `POST /cobertura/salarial` | `posicao`, `inicio`, `fim`, `titulacao` opcional. Consulta também posições/titulações ainda não cadastradas, retornando lacuna integral quando não há referência confirmada. |

Prévia: cada linha contém `original`, `dados`, `localizador`, `problemas`, `estado`, `versao`, usuário/data da revisão e os identificadores de referência salarial/componente ativados. Metadados de origem são imutáveis no lote; correção de origem deve gerar nova prévia. Relatórios locais exportados não devem ser versionados.

## Cobertura, migração e verificação

A cobertura inclui apenas referências confirmadas, separadas por posição histórica, vínculo, jornada e componente. As lacunas são inclusivas, inclusive em 29/02. Referências anteriores a 2020 são recortadas apenas na visualização. A consulta específica evidencia posição ou RT ausente. A visão geral abrange as estruturas cadastradas.

Mudanças de filtro, período, posição ou ID de referência limpam o resultado de cobertura ou de origem, reiniciam a paginação e descartam respostas pendentes.

A migração é aditiva e repetível: cria `estrutura_funcao`, `referencia_funcao`, `importacao_fonte` e `linha_importacao_fonte`, preservando as tabelas e referências anteriores. O startup executa a criação após o cadastro salarial. Antes da implantação, ensaie em cópia temporária e faça backup recuperável do banco; rollback de aplicação deve preservar as tabelas novas e os registros de revisão, sem apagá-los. Novas estruturas só participam de cálculos depois da conferência/ativação.

`test_official_sources.py`, `test_official_source_edges.py` e `OfficialSources.test.tsx` cobrem leitura, prévia, conflitos, ativação e lacunas. `integration_tests/test_official_sources_postgres.py` verifica precisão e exclusão concorrente com `TEST_POSTGRES_URL`.

Na importação PDF, contextos são globais para o leitor selecionado: intervalos de linhas são rejeitados, nunca ignorados. Diferenças entre blocos devem ser revistas por registro na prévia. O comparativo docente aceita somente as ordens de cabeçalho analisadas, inclusive a quebra em duas linhas; valores monetários precisam ser células completas com duas casas decimais.
