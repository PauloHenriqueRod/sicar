# Exercícios anteriores por parcelas

O perfil `parcelas_v1` de `exercicio_anterior` identifica origem do direito, competência, rubrica, categoria e natureza da folha devida. O RH confirma o direito, os efeitos financeiros, a regra aplicável e a pesquisa de pagamentos. O sistema não reconhece direito nem autentica documentos automaticamente.

## Contrato e fluxo

`GET /api/calculos/contratos/exercicios-anteriores` publica o JSON Schema autenticado. `POST /api/calcular` recebe `tipo_calculo="exercicio_anterior"` e `dados_extraidos={matricula, nome?, exercicios}`. O plano contém:

| Campo | Conteúdo |
| --- | --- |
| `vinculo_id`, `periodo` | Vínculo conferido e intervalo inclusivo do escopo. |
| `origens` | Identificação do direito, fonte/localizador, data documental opcional, intervalo de efeitos e regra com versão e vigência confirmada. A data documental não determina os efeitos. |
| `parcelas` | Origem vinculada, competência `YYYY-MM`, rubrica, categoria, período considerado, natureza da folha, nota e estado de revisão, estado da pesquisa de pagamentos. |
| `devidos` | Eventos identificados com valor confirmado, memória de cálculo, fonte e operação. |
| `recebimentos` | Pagamentos vinculados à parcela, identidade da origem e justificativa de vinculação. |
| `ajustes` | Valores explicitamente declarados com memória e regra específica confirmada. A lista inicialmente é vazia. |
| `documentos` | Fontes opcionais com matrícula/vínculo conferidos e decisões sobre candidatos extraídos. |
| `conferido_pelo_rh` | Confirmação explícita de revisão do processo. |

O motor acumula valores exatos e aplica HALF_UP na finalização. A memória conserva `devido_exato`, `recebido_exato` e `saldo_exato`. O [fluxo de revisão](fluxo-revisao-calculos.md) aceita entrada manual e exige nova confirmação após edições.

Demonstrativos suportados trazem competência (`MM/YYYY` ou `YYYY-MM`) e campos `Devido`, `Recebido`, `Férias/Abono` e `13o/13º/13_sal`. O leitor também aceita células de fichas financeiras reconhecidas. Apenas rubricas explícitas entram na revisão. Totais de coluna, dados ausentes e textos de decisões judiciais não geram pagamentos.

Em `candidatos_exercicios`, o RH associa pessoa e vínculo e aplica cada observação a devido, recebimento ou ajuste, ou justifica o descarte. A fonte e a magnitude são preservadas. Sinal negativo exige estorno, redução ou correção de sinal justificada. Origem do direito, via, operação e parcela exigem conferência.

## Identidades e conciliação

Cada parcela tem chave `(origem_direito_id, competencia, rubrica, categoria, natureza_folha_devida)`. Duplicar essa chave é inválido. Competência devida e período considerado precisam ser compatíveis com o escopo, efeitos e vigência. Principal mensal pertence ao próprio mês; reflexos têm categoria e período explícitos e não são gerados pelo nome da competência.

`LANCAMENTO`, `COMPLEMENTO` e `ESTORNO` são distintos. Complemento aponta a um lançamento original da mesma parcela; estorno aponta a original ou complemento da mesma parcela. Referências podem preceder a origem no JSON. Estornos acumulados não podem exceder o alvo. Mais de um devido original ativo na mesma parcela gera pendência; substituição integral pode ser representada por estorno total e novo evento.

Devidos repetidos são identificados por evento e parcela. Recebimentos de folha têm competência efetiva, rubrica efetivamente paga, naturezas de folha/rubrica, identificador de folha e sequência. Pagamento documental exige identificador próprio, sem folha ou sequência fictícias. A competência do pagamento pode ser posterior à competência do direito, desde que a vinculação seja justificada e conferida.

`identificador_pagamento` permite correlacionar comprovante documental e ficha quando comprovam o mesmo evento. A identidade física da folha continua sendo verificada mesmo se apenas uma cópia trouxer esse identificador. Cópias idênticas contam uma vez e mantêm os dados completos de cada fonte em `duplicidades_*`; divergências monetárias, de operação, vinculação ou referência geram pendência. Uma ponte entre eventos previamente distintos exige revisão, sem soma silenciosa. Sem identidade suficiente para provar repetição entre comprovantes distintos, a correlação permanece responsabilidade manual do RH.

`via_pagamento` aceita `NAO_INFORMADA`, `ADMINISTRATIVA` e `JUDICIAL`; processo e data são opcionais. Ausência desses dados não é convertida em pagamento administrativo. Informações fornecidas são preservadas inclusive em uma segunda fonte descartada do somatório por duplicidade.

A comparação considera os campos conhecidos de todas as fontes, em qualquer ordem. Via, processo, data ou identidade de folha incompatíveis geram pendência. Recebimento de natureza `D`, inclusive documental, exige revisão da operação. Documento sem natureza continua permitido. Estorno exige origem vinculada.

Os ajustes aceitam `identificador_evento` opcional, estável e distinto do ID da linha. Cópias do mesmo evento na mesma parcela contam uma vez e preservam suas fontes. Para compatibilidade com entradas anteriores sem esse campo, a identidade é composta por parcela, tipo, efeito, fonte/localizador e identificação/versão da regra. Divergências de valor, memória ou regra do mesmo evento geram `ajuste_exercicio_conflitante`. Eventos distintos comprovados podem ter identificações diferentes, mesmo citando o mesmo item da fonte. Se houver uma cópia sem identificação nesse item com vários eventos identificados, retorna `ajuste_exercicio_ambiguo`, sem vincular arbitrariamente. Quando uma fonte antiga não permite distinguir eventos, o RH precisa completar a identificação; o sistema não presume um novo ajuste apenas porque a linha tem outro ID.

`ajustes_declarados` mantém todas as entradas, `ajustes_considerados` identifica os eventos efetivamente somados e `duplicidades_ajustes` registra as cópias com seus dados completos. Os IDs da memória da parcela correspondem aos eventos considerados, permitindo reproduzir o saldo sem somar fontes repetidas.

## Pendências, saldo e limites

`estado_revisao`: `PENDENTE`, `CONFERIDO` ou `ENCAMINHADO`, com nota obrigatória. São registros declarados da revisão do RH, sem workflow automático de decisão jurídica. `pesquisa_pagamentos`: `PENDENTE`, `IDENTIFICADOS` ou `NAO_HOUVE_CONFIRMADO`. Ausência de lançamentos não confirma ausência de pagamentos. Valor desconhecido permanece `null`/ausente e bloqueia a apuração; zero confirmado exige lançamento com fonte e memória.

Para cada parcela, o motor calcula:

`principal = devidos originais + complementos devidos − estornos devidos`

`devido = principal + ajustes de acréscimo − ajustes de redução`

`recebido = pagamentos originais + complementos pagos − estornos pagos`

`saldo = devido − recebido`

Não há prescrição automática pela idade da competência, nem juros, índices de atualização ou descontos genéricos. Ajustes são valores manuais explicitamente fundamentados e conferidos, não um motor de atualização legal. Redução superior ao devido gera pendência; saldo negativo decorrente de pagamento superior ao devido é preservado, sem corte em zero.

Exemplo sintético: devido original 1000, complemento 100, estorno do complemento 40; pagamento 200, complemento pago 50, estorno pago 10. Devido = 1060, recebido = 240, saldo = **820,00**. A memória lista os eventos, alvos, fontes, regra, revisão, parcelas e totais, permitindo reprodução independente.

O resultado contém `tipo_exercicio="parcelas_v1"`, `parcelas`, eventos considerados, ajustes declarados, duplicidades, totais e `saldo_parcelas_calculadas`. O alias `total_geral_a_receber` preserva integração, sem prometer líquido completo. Entradas decimais, resultado e versão do motor são persistidos no histórico; repetição idempotente não cria novo cálculo. Pendências retornam 400 com código específico e localização `dados_extraidos.exercicios`, sem salvar cálculo incompleto. Exemplos: `lancamento_exercicio_pendente`, `lancamento_exercicio_conflitante`, `devido_exercicio_duplicado`, `origem_direito_exercicio_pendente`, `revisao_exercicio_pendente`, `ajuste_exercicio_sem_regra`, `candidato_exercicio_pendente`.

Limites técnicos: 600 competências, 100 origens, 1000 parcelas, 2000 devidos, 2000 recebimentos, 200 ajustes, 10 documentos e 200 candidatos por documento. Extração acima de 200 candidatos avisa que é incompleta; o operador precisa conferir a fonte inteira. Limites globais de corpo, resultado e relatório permanecem vigentes; processos extensos podem precisar ser divididos para exportação.

## Compatibilidade e validação

`fluxo_mensal/fluxo` e o leitor CSV agregado anterior continuam aceitos, com sua estrutura e fórmula antigas. A resposta da API identifica esse perfil como `resumo_legado_v1` e informa sua limitação. Não há migração automática de totais antigos para rubricas, origem do direito ou pagamentos identificados. A interface atual utiliza o perfil por parcelas para entrada manual e extração atual; respostas de servidores antigos sem candidatos preservam revisão agregada com aviso de legado. Dados e históricos antigos não são reescritos.

`test_exercicios_parcelas.py`, `ExerciciosForm.test.tsx` e `App.exercicios.test.tsx` cobrem saldos, acertos, revisão e percurso entre leitura, API e PDF com dados sintéticos.
