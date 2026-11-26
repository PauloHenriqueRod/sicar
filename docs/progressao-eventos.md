# Progressão TAE/docente por eventos

O contrato `eventos_v1` combina a [apuração por períodos](apuracao-periodos.md), as [referências salariais](referencias-salariais.md) e a política `decimal_half_up_final_v3`. Para concessões compartilhadas, consulte [adicionais explícitos](adicionais-explicitos.md).

## Fluxo e modalidade

A ficha mostra os pagamentos observados. A ata é fonte complementar para conferir o enquadramento e a data de efeitos. A data da reunião, sozinha, não estabelece efeitos financeiros. A seção de ata permite anexar o documento ou preencher os campos manualmente. Consulte os [leitores suportados](extracao-documentos-rh.md).

Na primeira extração, uma ficha inequívoca pode sugerir nome e matrícula nos campos vazios, com a origem preservada. Em rascunho sem identificação e sem aplicação anterior, o RH pode acionar **Preencher identificação a partir da ficha**. A reextração preserva edições e campos apagados. Titulação observada exige conferência de origem ou destino. Cada edição exige nova confirmação.

Uma portaria individual de progressão docente compatível com a identificação do processo sugere **Docente** e preenche **Início da apuração** com a data expressa de efeitos financeiros. As duas sugestões ficam vinculadas aos campos de origem para revisão. Uma data ausente ou ambígua fica em branco. A data de emissão e a data de publicação não substituem os efeitos. Em um rascunho, use **Usar sugestões da portaria de progressão** para aproveitar novos dados em campos vazios.

Escolha explicitamente **TAE** ou **DOCENTE**. Informe a posição completa de origem: carreira, vínculo, jornada, versão histórica da carreira e classificação/capacitação/padrão TAE ou classe/nível docente. TAE informa escolaridade e percentual inicial de IQ; docente informa a titulação correspondente à RT, inclusive quando a RT confirmada for zero. Anuênio inicial exige confirmação numérica, inclusive zero. O adicional usa concessão explícita e confirmação própria quando selecionado; o percentual inicial legado só é exigido por sua fórmula legada.

VB e IQ (TAE) ou VB e RT (docente) são componentes distintos. Percentuais positivos de anuênio/adicional exigem suas próprias rubricas. Não se repete uma fórmula sob dois códigos para duplicar a diferença. Correções individuais de VB/RT não dispensam referências salariais confirmadas: posição, jornada, titulação e vigência continuam verificadas, inclusive quando ambos os componentes foram corrigidos.

### Correção individual de VB/RT

A origem aceita `vb_manual` e `rt_manual`, cada um com `valor`, `fonte`, `localizador` e `justificativa` obrigatória neste fluxo. RT permanece exclusiva de docente. O cadastro global não é alterado. As fontes do segmento conservam a referência confirmada com `valor_decimal` original e a correção `manual_conferida` com `valor`, `valor_sugerido`, `referencia_id` e justificativa. Só o valor revisado alimenta a diferença; a apresentação monetária permanece arredondada apenas no final.

O evento independente `BASE` altera somente `vb_manual` e/ou `rt_manual`, com data de efeitos e regra histórica. Propriedade ausente mantém o componente anterior; `null` explícito retorna à tabela. Evento sem alterações é inválido. A interface não presume retorno de componentes não selecionados. Mudança de posição retira bases manuais anteriores e mudança de titulação retira a RT manual; nova correção pode ser declarada por evento próprio, inclusive na mesma data, sem misturar progressão com IQ/RT. A base de comparação permanece a origem revisada e é validada pelas referências vigentes em cada segmento.

Exemplo sintético docente em fevereiro/2024: origem revisada VB=3.000 e RT=600; destino VB=5.800 e RT=1.160 desde 15/02, RT=1.740 desde 20/02. Diferença: `2800×15/29 + 560×5/29 + 1140×10/29 = 56200/29`, finalizada em **1.937,93**. As tabelas originais (VB=2.900 e RT=580 na origem) ficam preservadas. Testes independentes verificam esse resultado, eventos de correção/retorno, incompatibilidades e referências ausentes.

## Linha do tempo e comparação

O período tem primeiro e último dia inclusivos, informados pelo RH. Data do documento e implantação são metadados, distintos dos efeitos financeiros. Eventos disponíveis:

| Tipo | Alterações permitidas |
| --- | --- |
| `PROGRESSAO` | Objeto completo da nova posição; pode incluir jornada concedida na mesma data. |
| `JORNADA` | Somente jornada da posição corrente, em objeto completo. |
| `IQ` | Nova escolaridade (`titulacao`) e percentual de IQ; exclusivo de TAE. |
| `RT` | Nova titulação; exclusiva de docente. |
| `ADICIONAL` | Concessão completa do adicional (espécie, percentual, base, vigência e regra). O percentual isolado permanece aceito somente para compatibilidade. |
| `ANUENIO` | Percentual de anuênio confirmado. |

Uma mudança de IQ ou RT não é embutida no evento de progressão. Eventos de campos distintos na mesma data são aplicados conjuntamente; mudanças concorrentes do mesmo campo são rejeitadas. Carreira e vínculo permanecem os de origem. O sistema não determina se uma progressão ou concessão é juridicamente devida.

Cada regra de cálculo declara identificador, versão, fonte e vigência, sem assumir que publicação e efeitos coincidem. A regra da rubrica cobre a janela calculada; a regra de cada evento deve abranger sua data de efeitos; a regra do reflexo deve abranger sua data-base. Esses dados são conferidos pelo RH, sem autenticação automática do ato pelo sistema.

A cada segmento, calcula-se:

`diferença = (valor mensal após os eventos − valor mensal da origem) × dias computados / dias reais do mês`

A posição, titulação e percentuais de origem constituem a comparação explícita, sem os eventos concedidos. Ambos os lados consultam suas tabelas vigentes naquele segmento. Assim, um reajuste geral não congela o salário de origem no valor de uma única data. Lacunas de origem/destino, jornada incompatível ou RT ausente geram pendência específica, sem salário presumido. Se uma posição histórica não possuir referência aplicável, o RH precisa resolver a referência ou separar o período; o motor não inventa reenquadramento.

As divisões incluem viradas de mês/ano, vigências salariais, progressão, jornada, IQ, RT e adicionais. Cada interrupção declara regra histórica cuja vigência cobre todos os seus dias, inclusive os limites. Interrupções sobrepostas excluem o dia uma única vez. Cada segmento preserva regras e tabelas com os papéis `ORIGEM` e `DESTINO`, além dos valores mensais e frações exatas por componente.

**Recebimentos representam diferenças já pagas**, identificadas por competência, rubrica, natureza, folha e sequência. Não se informa a remuneração integral mensal como pagamento de diferença. Duplicidades, complementações e estornos seguem o contrato comum; os pagamentos são abatidos uma vez.

## Reflexos explícitos

Nenhum nome de mês, início do ano ou quantidade padrão gera férias ou 13º. Cada reflexo informa tipo, data-base, competência, avos inteiros (1–12), componentes da base, rubrica/natureza e regra histórica. A base é a soma exata das diferenças **mensais** dos componentes escolhidos na data-base:

- `FERIAS_UM_TERCO`: base × avos / 36.
- `DECIMO_TERCEIRO`: base × avos / 12.

O RH determina direito, componentes e avos. Não se adquire um avo automaticamente por existir um mês no intervalo genérico. Para o mesmo tipo, data-base, competência, rubrica e naturezas, é possível separar componentes sem sobreposição e atribuir avos próprios a cada parcela: por exemplo, VB com 12/12 e RT com 6/12. IDs repetidos e componentes repetidos entre essas parcelas são rejeitados, inclusive quando avos ou ordem da lista são diferentes. Diferenças negativas são preservadas, permitindo devoluções conforme a análise manual do RH.

O componente `ADICIONAL_CONFIRMADO` exige origem da concessão, período de referência e lista explícita de pagamentos anteriores no reflexo, inclusive lista vazia conferida. A base/regra só é exigida se utilizada. Para apurar somente seus reflexos, use `apurar_principal=false` na rubrica do adicional. A reserva do principal/reflexo é compartilhada com o fluxo de adicionais para rejeitar períodos já apurados. Correções usam `substitui_historico_id`, preservam a versão anterior e substituem atomicamente a cobertura; snapshots completos da versão substituída continuam exportáveis com identificação de versão histórica. Veja o contrato e as limitações do acervo legado em [Adicionais explícitos](adicionais-explicitos.md) e [Memória de cálculo](memoria-calculos.md).

## Exemplos independentes

Todos os exemplos são sintéticos ou valores de teste sem identificação pessoal; não constituem tabelas oficiais ou homologação do direito.

| Cenário | Memória independente | Resultado final |
| --- | --- | --- |
| TAE, fevereiro/2024; VB 2.900 → 5.800 em 15/02; IQ 10% → 20% em 20/02 | VB: 2.900×15/29 = 1.500; IQ: 290×5/29 + 870×10/29 = 350 | 1.850,00 |
| Mesmo TAE, IQ em 11/02 | VB: 1.500; IQ: 290×4/29 + 870×15/29 = 490 | 1.990,00 |
| Docente, VB 2.900 → 5.800 em 15/02; RT 580 → 1.160 pela progressão; RT de nova titulação 1.740 em 20/02 | VB: 1.500; RT: 580×5/29 + 1.160×10/29 = 500 | 2.000,00 |
| TAE, 14 dias de fevereiro/2023; VB 1 → 1,01 e IQ de 100% | 0,01×14/28 + 0,01×14/28 = 0,01 | 0,01, embora cada componente apresentado seja 0,01 |
| Referência numérica de teste, janeiro/2026; VB 3.686,33 → 3.833,79; IQ 30%; 14 dias, férias e 13º explicitamente com 12/12 | Diferença mensal exata: 147,46 + 44,238 = 191,698; principal: 191,698×14/31; férias: 191,698/3; 13º: 191,698 | Principal 86,57; férias 63,90; 13º 191,70; total acumulado exato apresentado em 342,17 |

Todos os valores usam `Decimal` convertido diretamente em `Fraction`. Nenhum valor já apresentado com duas casas alimenta outra parcela ou o total. A apresentação final aplica meio centavo para longe de zero. Valores monetários públicos são textos decimais, preservados no histórico, na tela e no PDF.

## Contrato e compatibilidade

`POST /api/calcular` continua com `tipo_calculo="progressao"`, agora com `dados_extraidos.progressao`. O plano contém `modalidade`, `periodo`, `estado_inicial`, `eventos`, `rubricas`, `recebidos`, `reflexos` e `conferido_pelo_rh=true`. `GET /api/calculos/contratos/progressao` fornece o JSON Schema autenticado do novo contrato. Campos desconhecidos, mistura com fatores legados e ausência de confirmação são rejeitados.

O payload agregado anterior permanece aceito para compatibilidade dos consumidores existentes, com seu contrato e resultados anteriores. A interface de novos processos usa exclusivamente o plano por eventos. Históricos antigos não são regravados nem recebem datas presumidas. A extração antiga não comprova as datas independentes: os dados faltantes são preenchidos manualmente na revisão.

O novo resultado mantém `tipo_apuracao="periodos_v1"` e acrescenta `tipo_progressao="eventos_v1"`, modalidade, estado de origem e reflexos explícitos. O histórico indexa a posição e titulação iniciais declaradas. A idempotência compara Decimal por valor e preserva a comparação exata dos identificadores e das alterações explícitas.

O contrato admite até cinco componentes mensais e cem reflexos, além dos [limites comuns](apuracao-periodos.md). `tests/test_progressao_eventos.py` contém exemplos independentes de ambas as modalidades.

## Bases mensais da ficha financeira docente

Na revisão simplificada de progressão docente, o RH confere o VB e a RT integrais pagos em cada competência, da data dos efeitos até o último dia considerado. A ficha sugere a rubrica 00001 para VB e a 82606 para RT quando houver uma única ocorrência regular de rendimento, sequência zero, do mesmo docente e vínculo. Ausência ou conflito deixa a base pendente para preenchimento com fonte e justificativa. O RH pode corrigir uma sugestão ou informar zero confirmado. Meses sem ficha também admitem preenchimento manual.

O contrato das rubricas simplificadas exige `bases_mensais_origem` com uma linha por competência, identificador estável, `vb`, `rt` e `base_mensal_integral_confirmada`. Cada componente registra valor decimal, fonte, localizador e justificativa. A posição, a jornada e a titulação conferidas determinam a referência vigente no destino. Em cada segmento, o motor calcula separadamente (base de destino − base paga) × dias considerados / dias reais do mês. Somente a diferença proporcional segue para o saldo.

Se a cobertura da ficha termina antes da data final escolhida, o RH pode completar as competências restantes ou limitar a apuração ao último mês consecutivo com VB e RT na ficha. A segunda opção altera o fim do período apenas quando acionada.

A consulta autenticada `POST /api/calculos/progressao/previa-folha` recebe o plano conferido, sem documentos nem identificação pessoal, e executa o mesmo motor em leitura. Por segmento e componente, apresenta o pago mensal, o destino mensal, a fonte da tabela e a diferença do período. A exportação obtém essas informações dos segmentos salvos. A versão anterior do histórico permanece disponível após um recálculo.

A base mensal deve representar remuneração integral conferida, e não uma parcela proporcional/complementar isolada. Meses mistos exigem reconstrução e revisão pelo RH; o leitor não anualiza nem soma estornos automaticamente. Zero é explícito. Pagamentos anteriores de diferenças são discriminados em `recebidos`.

Reflexos de férias/13º mantêm a comparação da posição de origem e suas fontes próprias, identificadas como `ORIGEM_REFLEXO`; a implantação do VB novo na folha regular não comprova pagamento da diferença do reflexo. A memória preserva `bases_mensais_origem`, valores exatos por segmento e referências; arredondamento permanece somente nos resultados monetários finais. Os contratos detalhados com rubricas numéricas continuam admitindo comparação entre posições ou a lista histórica de VB por competência.

Na progressão docente com ficha financeira, a conferência começa pelas rubricas por competência, pelo período, pelo percentual inicial de anuênio e pelo 13º. Cada correção guarda o valor extraído, o valor conferido, a página e o motivo. Uma edição atualiza os campos já vinculados àquela ocorrência e exige nova conferência. O RH pode usar o VB como base integral do mês e confirmar esse uso. O percentual de anuênio é editável junto às datas e exige zero explícito quando não houver anuênio. A conferência das fontes, do enquadramento e das rubricas ocorre na mesma tela. Após as confirmações, o RH pode calcular diretamente.

Na revisão mensal, uma confirmação do RH abrange os documentos usados para o mesmo docente e vínculo. O nome e a matrícula permanecem editáveis. A revisão bloqueia documentos com identificação incompatível e mantém a associação e a origem dos valores na memória. Quando o vínculo documental está ausente, a matrícula identifica a associação local ao cálculo.

A posição de origem aparece acima da nova classe e do novo nível. A revisão sugere a origem explícita da portaria de progressão ou, na sua ausência, a classe e o nível inequívocos do cabeçalho docente da ficha. A consulta autenticada `GET /api/tabelas/posicoes-docentes` utiliza a data inicial e admite filtros por carreira, jornada, classe, nível e VB. Se a posição estiver incompleta, o VB inicial pode sugerir um enquadramento único na tabela vigente. O RH pode escolher a referência quando houver ambiguidade e conferir a titulação usada para a RT. O ato pode fornecer a classe e o nível de destino e a data dos efeitos. O motor verifica a vigência das duas posições.

Na conferência simplificada, as diferenças regulares são identificadas na memória por `DIF-VB`, `DIF-RT` e, quando houver anuênio, `DIF-ANUENIO`. São identificadores internos de cálculo. A regra de comparação é registrada para o intervalo revisado pelo RH. O 13º continua sendo incluído expressamente. Casos com outros eventos, interrupções ou pagamentos anteriores usam a apuração detalhada com rubricas identificadas de folha. Os contratos anteriores com códigos numéricos continuam válidos.

Quando a apuração do Magistério Superior efetivo atravessa 1º de janeiro de 2025, o motor correlaciona as posições em vigor em 31 de dezembro na origem e no destino entre as estruturas cadastradas `MS até 2024` e `MS desde 2025`. A memória conserva as duas posições, a regra e as referências de VB e RT de cada segmento. A base individual do enquadramento antigo termina na transição. Uma base de VB conferida especificamente para a nova competência continua aplicável. Promoções individuais dependem de evento próprio. [Lei nº 15.141/2025, Anexo LXXVIII, item c](https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2025/lei/anexo/anexo1a100-lei15141.htm)

O PDF da progressão estruturada apresenta os saldos salvos por competência e rubrica, com os segmentos, reflexos e pagamentos considerados. Cada segmento remete a um catálogo das regras, estados e bases usados. Os documentos são identificados pelo nome; campos utilizados ou corrigidos incluem a página e os valores. A extração integral continua disponível no histórico com as permissões do registro.
