# Substituição por períodos, funções e opção confirmada

## Escopo e conferência

O fluxo usa o calendário real da issue #20 e as referências confirmadas CD/FG/FCC da issue #19. A conferência documental, a composição aplicável a cada opção e o direito permanecem manuais pelo RH. As operações aritméticas disponíveis não autorizam uma opção legal nem presumem percentual, função própria, afastamento ou pagamento.

O usuário pode iniciar sem PDF. Documentos enviados juntos alimentam um único processo de substituição, em vez de um cálculo por arquivo. Os dados de negócio e os candidatos extraídos são editáveis. Alterar os dados retira a confirmação e invalida o resultado anterior. Editar um resultado salvo vincula a nova tentativa ao histórico anterior como revisão explícita.

## Contrato

`POST /api/calcular` mantém `tipo_calculo="substituicao"`. O novo contrato usa `dados_extraidos.substituicao` e matrícula do substituto em `dados_extraidos.matricula`. O JSON Schema autenticado está em `GET /api/calculos/contratos/substituicao`.

| Campo do plano | Conteúdo |
| --- | --- |
| `periodo` | Início e último dia incluído da janela financeira. |
| `designacao` | Intervalo, ID, motivo, documento de origem e localizador. |
| `titular_matricula` | Identificação do titular, distinta da matrícula do substituto. |
| `afastamentos_titular` | Intervalos documentados; não se presume afastamento em toda a designação. |
| `impedimentos_substituto` | Férias e outros impedimentos com ID, motivo, origem e localizador; lista vazia exige conferência final. |
| `estado_inicial` | Função substituída, situação da função própria e opção remuneratória. |
| `eventos` | Mudanças completas de função/composição/opção, com efeitos financeiros e origem. Data do documento e implantação são metadados separados. |
| `rubrica` | Código, natureza da folha e natureza de rubrica. |
| `recebidos` | Pagamentos, complementos e estornos identificados; lista vazia precisa ser conferida. |
| `documentos` | Nome do arquivo, papel, pessoa identificada, matrícula/nome observados e candidatos. Não guarda o PDF. |
| `conferido_pelo_rh` | Booleano `true`, explicitamente confirmado. |

Cada função informa `tipo_funcao`, `codigo_funcao`, `modalidade` e uma lista de componentes distintos. Cada componente exige `percentual_utilizado` explícito, inclusive 100 quando integral, e origem `TABELA` ou `MANUAL`. O TOTAL não pode ser somado aos componentes que já o compõem.

Na origem `TABELA`, a identidade completa seleciona referências pela vigência, sem congelar o valor de uma referência escolhida na interface. O serviço lê os componentes necessários em uma consulta, preservando os limites das referências e distinguindo lacunas. O cadastro anterior a 2020 pode atender ao início do escopo quando sua vigência o permite. Não há salário ou valor de função de fallback.

Na origem `MANUAL`, são obrigatórios valor decimal, fonte, localizador e início de vigência. O fim é opcional. A vigência manual deve cobrir todos os dias calculados. Não se mistura valor manual com datas/valor presumidos de tabela.

A função própria tem situação explícita `SEM_FUNCAO_CONFIRMADA` ou `COM_FUNCAO`, esta acompanhada da composição completa. Ausência de informação não significa ausência de função.

## Opção remuneratória

O objeto `opcao` contém identificador, versão, fonte, início/fim dos efeitos, `confirmada=true`, operação e tratamento da diferença mensal negativa. São suportadas as operações fechadas:

- `DIFERENCA_FUNCOES`: base substituída menos base da função própria;
- `BASE_SUBSTITUIDA`: somente a base substituída, conforme composição explicitamente conferida.

A base é a soma dos componentes selecionados, cada um multiplicado pelo percentual informado. O sistema não deduz opção por rótulo, razão entre valores ou código da função. O RH precisa conferir quais componentes, percentuais e operação correspondem à regra do caso. Componentes não disponíveis no cadastro podem ser informados com fonte manual. Não há execução de expressões arbitrárias nem catálogo de todos os regimes legais pré-homologado.

`diferenca_negativa="ZERAR"` limita o devido mensal a zero; `PERMITIR` preserva a diferença negativa. Essa escolha também exige regra conferida. A política não limita o saldo após pagamentos: um pagamento maior que o devido pode resultar em devolução.

## Cruzamento e memória

O período aplicável é a interseção da janela financeira com a designação e a união dos afastamentos do titular. Sobre ele são excluídos os impedimentos do substituto. Intervalos parcialmente externos são recortados; intervalos totalmente externos não descontam dias. Afastamentos e impedimentos sobrepostos não repetem dias.

A segmentação inclui mudanças de mês/ano, início/fim da designação, afastamentos, impedimentos, eventos, regras, valores manuais e referências de função. Alterar somente o valor da função já produz novo segmento, mesmo sem mudança de código. Eventos concorrentes com a mesma data são rejeitados: informe um único novo estado completo nessa data.

Cada segmento registra limites inclusivos, dias de calendário, dias considerados/excluídos, motivos, fontes dos afastamentos e impedimentos, composição, regra e referências efetivas. O resumo por competência agrupa combinações de motivos; não soma novamente dias em que coexistem férias e outro impedimento. Exemplo: cinco dias de férias e cinco de licença com três coincidentes excluem sete dias, não dez.

Ausência total de interseção produz `periodo_sem_intersecao`. Todo o período elegível impedido produz devido zero, mantendo a memória e os pagamentos a reconciliar. Lacuna de função ou vigência manual/opção insuficiente produz pendência específica apenas nos segmentos que precisam de cálculo. Não se consulta a base própria quando a operação confirmada não a utiliza.

O valor de cada segmento é `base mensal confirmada × dias considerados / dias reais da competência`. A acumulação usa Fraction a partir de Decimal, sem arredondamento intermediário; a apresentação aplica duas casas e meio centavo para longe de zero. A soma dos valores apresentados pode diferir do total calculado com precisão interna.

Os recebimentos seguem a conciliação comum: competência, rubrica, naturezas, folha, sequência e operação. Cópias são identificadas sem deduzir novamente o pagamento; complementos distintos permanecem; estornos precisam apontar para o pagamento original e não podem excedê-lo. Os pagamentos são abatidos uma vez depois de somar os segmentos, com devido, recebido e saldo discriminados por competência.

Os recebimentos podem pertencer a folhas de natureza diferente da devida (por exemplo, NORMAL e SUPLEMENTAR), mantendo a mesma rubrica e natureza de rubrica. A memória preserva cada natureza de folha e o total concilia todos os lançamentos aceitos, sem duplicar cópias.

## Extração e acesso às referências

O leitor aceita períodos explicitamente rotulados como designação, afastamento do titular, férias ou impedimento do substituto, com datas completas ISO ou brasileiras separadas por `a` ou `até`. O RH identifica a pessoa e o papel de cada documento. Matrícula divergente exige revisão. Férias sem indicação de pessoa não geram impedimento automático.

A rubrica 83185 fornece candidatos por competência, natureza, sequência e valor. Colunas TOTAL ficam fora. O RH associa a ficha do substituto e confirma folha e operação em `recebidos`. Até 100 períodos e 200 pagamentos são exibidos por documento. Excedentes geram `dados_extraidos.alertas_extracao` para conferência e preenchimento manual.

`GET /api/calculos/referencias-funcao?inicio=AAAA-MM-DD&fim=AAAA-MM-DD&pagina=1` oferece consulta autenticada de componentes confirmados, com paginação de 100 registros. Não concede permissão de importar, editar ou ativar tabelas; os endpoints administrativos permanecem admin/dev. A interface descarta respostas de consultas cujo período foi alterado e permite entrada manual quando não há cobertura.

## Histórico, exportação e compatibilidade

O resultado `tipo_substituicao="periodos_v1"` indexa a função inicial e preserva toda a linha do tempo no histórico cifrado. Uma revisão usa `dados_extraidos.substitui_historico_id` de outra substituição da mesma matrícula, conforme as permissões da [memória de cálculo](memoria-calculos.md). O PDF discrimina os componentes salvos. Processos extensos podem exigir divisão do período para exportação.

O contrato agregado continua aceito. O CSV legado apresenta candidatos e alertas. Código, valor da função, ano e dias exigem conferência.

## Casos independentes e verificações

Exemplo sintético: março/2024, designação de 1 a 31, titular afastado de 5 a 25, férias do substituto de 8 a 12 e licença de 10 a 14. São 21 dias aplicáveis, sete impedidos e 14 considerados. Função própria de 1.000; função substituída de 4.100 até 15/03 e 7.200 desde 16/03. Com a opção sintética de diferença confirmada: `3.100×4/31 + 6.200×10/31 = 2.400,00`. Pagamento anterior de 500 resulta em saldo de 1.900,00.

`tests/test_substituicao_periodos.py` cobre o exemplo, mudanças de função, calendários, impedimentos, acertos e histórico. `integration_tests/test_substitution_functions_postgres.py` verifica componentes e vigências em PostgreSQL.
