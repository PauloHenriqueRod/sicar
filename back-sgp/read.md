# DOCUMENTO DE ESPECIFICAÇÃO TÉCNICA E FÓRMULAS DE CÁLCULO

> **Motor 2026-11-03.1:** progressão docente aceita bases mensais integrais de VB conferidas por competência na ficha financeira. Consulte [contrato, limites e distinção dos reflexos](../docs/progressao-eventos.md).

> **Memória de cálculo:** [snapshots, recálculos vinculados e equivalência da exportação](../docs/memoria-calculos.md). Versões antigas permanecem consultáveis; recálculos inserem novos registros sem alterar o snapshot anterior.

> **Motor 2026-10-31.2:** [progressão com correções individuais rastreáveis de VB/RT](../docs/progressao-eventos.md), mantendo referências confirmadas e arredondamento final. [Revisão dos cálculos](../docs/fluxo-revisao-calculos.md): compatibilidade de repetição entre histórico de aplicações ausente e vazio, sem ignorar histórico preenchido.

> **Atos opcionais (31/10/2026):** [layouts oficiais delimitados, fontes e limites](../docs/extracao-atos-portarias.md). Envelope atual `rh_paginas_v5`, com leitores por layout e compatibilidade dos históricos, preservando papéis e datas; conferência documental/do direito permanece manual pelo RH.

> **Extração por página (31/10/2026):** [extracao-documentos-rh.md](../docs/extracao-documentos-rh.md) descreve o contrato comum, layouts delimitados, associação manual de pessoa/vínculo, processamento parcial do lote e preservação das fontes no cálculo revisado. Extração não confirma autenticidade, direito ou quitação.

> **Exercícios anteriores — perfil `parcelas_v1` (30/10/2026):** o contrato atual está em [exercicios-parcelas.md](../docs/exercicios-parcelas.md). Devido, recebido, saldo, origem do direito e revisão são identificados por parcela. Pagamentos administrativos/judiciais informados são preservados; dados ausentes permanecem pendentes. Prescrição, juros, atualização e descontos exigem regra específica confirmada e valor declarado. As fórmulas agregadas descritas abaixo permanecem como compatibilidade legada, sem conversão automática para o novo contrato.

> **Motor 2026-10-28.1:** o contrato comum de intervalos, eventos e parcelas está em [apuracao-periodos.md](../docs/apuracao-periodos.md). A [progressão TAE/docente por eventos](../docs/progressao-eventos.md) utiliza esse núcleo, separando datas de progressão e IQ/RT, referências históricas e reflexos explícitos. A conferência documental e do direito continua manual pelo RH; não são presumidas datas a partir dos fatores dos contratos legados.
## SISTEMA DE AUTOMAÇÃO DE PROCESSOS DE RH — SUPERINTENDÊNCIA DE GESTÃO DE PESSOAS

---

### Histórico de Revisões
| Versão | Data | Autor | Descrição |
| :--- | :--- | :--- | :--- |
| 1.0.0 | 18/06/2026 | Engenharia de Software | Consolidação de fórmulas extraídas por engenharia reversa das planilhas de RH legadas e definição de arquitetura para o MVP. |

---

## 1. INTRODUÇÃO E ESCOPO

[cite_start]Este documento estabelece as especificações matemáticas, as regras de validação lógica e as diretrizes arquiteturais para a migração dos procedimentos analíticos da Superintendência de RH de planilhas eletrônicas (Microsoft Excel) para uma solução web integrada baseada em FastAPI (Python) e React[cite: 19, 26, 29].

[cite_start]O objetivo primário do sistema é mitigar a ocorrência de erros operacionais de cálculo em folha [cite: 25][cite_start], acelerar a ingestão de dados cadastrais por meio de processamento automatizado de documentos em PDF [cite: 19] [cite_start]e garantir a rastreabilidade absoluta de todas as decisões administrativas tomadas pela Secretaria de Gestão de Pessoas (SGP)[cite: 27, 38].

---

## 2. ARQUITETURA DE REFERÊNCIA DO MOTOR DE CÁLCULO

[cite_start]Para garantir a acurácia decimal exigida em cálculos de folha de pagamento, o motor de cálculo obedecerá às seguintes premissas técnicas[cite: 22, 24]:
* **Precisão monetária:** A política `decimal_half_up_final_v3` (motor `2026-10-26.3`) aplica `ROUND_HALF_UP` somente na finalização monetária. Bases, diferenças, proporcionalidades, pagamentos recebidos e reflexos mantêm precisão interna antes da soma. A leitura dos números JSON usa `Decimal` sem conversão intermediária para `float`; o contrato de saída continua numérico. A apresentação de cada parcela usa duas casas, mas essa versão apresentada não alimenta os totais. Por isso, a soma visual das parcelas pode diferir do total, conforme nota exibida na tela e no relatório. As referências qualificadas usam `Numeric(30,12)`, com vigência e dimensões explícitas; as tabelas anuais `Float` são preservadas apenas como legado pendente. Consulte [o contrato e a migração](../docs/referencias-salariais.md). O salário composto por VB e RT não é arredondado antes do cálculo.
* **Reprodução e compatibilidade:** O snapshot registra entradas decimais textuais, referências salariais efetivamente usadas, versão do motor, calendário e política de arredondamento. Tentativas repetidas com a mesma chave retornam o resultado salvo, inclusive quando produzido pela versão anterior; escalas equivalentes como `1`, `1.0` e `1.00` não caracterizam alteração. Uma nova execução gera outro registro, preservando os anteriores. A vinculação explícita entre recálculos permanece no escopo da issue de memória/histórico.

Exemplo: diferença de VB de `148,85`, IQ de `25%` (`37,2125`) e anuênio de `4%` (`5,9540`) totalizam internamente `192,0165`, finalizado em **R$ 192,02**. Dez meses usam `192,0165 × 10 = 1.920,165`, finalizado em **R$ 1.920,17**, sem multiplicar o mensal exibido de R$ 192,02. Empates positivos e negativos seguem a mesma regra: `2.674,495 → 2.674,50` e `-2.674,495 → -2.674,50`. Divisões de principal e reflexos são combinadas em um numerador comum antes da divisão final para preservar empates exatos.
* **Calendário implementado:** Os divisores proporcionais usam os dias reais do mês de referência, incluindo fevereiro em anos bissextos. Não há integração implementada com calendários de feriados ou apuração automática de dias úteis.
* [cite_start]**Interface de Conferência:** Toda massa extraída dos documentos será submetida a uma camada transicional editável no React antes de sofrer persistência final[cite: 19, 30].

---

## 3. ESPECIFICAÇÃO DETALHADA DOS 6 FLUXOS DE CÁLCULO

### Origem e conferência dos dados

| Dado | Fonte primária | Regra de extração/conferência |
| :--- | :--- | :--- |
| Matrícula e nome | Ficha financeira | Cabeçalho `Nome: matrícula - nome`, sem confundir com os dados do responsável pela emissão. |
| Valores recebidos | Ficha financeira | Valores mensais da rubrica relacionada ao cálculo, incluindo vencimento, RT/IQ, insalubridade, periculosidade, anuênio e abono. |
| Anuênios | Ficha financeira | Campo `T. serv.` no canto superior direito, quando preenchido. |
| Cargo, classe e nível atuais | Ficha financeira | Linha `Cargo/Lotação`; quando necessário, conferir o vencimento básico com a tabela da carreira. |
| Adicional ocupacional | Ficha financeira e concessão conferida pelo RH | Valor da rubrica; a razão adicional/VB gera apenas sugestão revisável. Espécie, percentual, base, regra e vigência exigem confirmação. VB e RT permanecem discriminados. |
| Função gratificada/cargo de direção | Ficha financeira | Campo `Função/Exerc.`. |
| Interrupção de substituição | Programação de férias | Dias de férias concomitantes ao período de substituição são descontados dos dias substituídos. |
| Abono de permanência | Ficha financeira e direito confirmado pelo RH | `98002 - CONT. PLANO SEGURIDADE SOCIAL` é fonte do desconto; sua presença não concede abono nem confirma valor elegível. Apurar parcelas e pagamentos anteriores pelo contrato vigente. |
| Datas de concessão/rescisão, período e destino da progressão | Ato da reitoria, portaria ou documento de concessão | Dado externo sujeito à revisão antes do cálculo. |
| Entrada em exercício de substituto | Cadastro funcional | Campo `EXERCICIO` da seção `CARGO EMPREGO`. |

Toda extração permanece sujeita à conferência humana. Campos vindos de documentos distintos devem preservar sua fonte para que divergências possam ser verificadas.

[cite_start]O sistema oferecerá suporte a 6 fluxos distintos de cálculos para professores e servidores, baseados nas regras de negócio extraídas das planilhas Excel[cite: 23]:

### FLUXO 1: CÁLCULO DE SUBSTITUIÇÃO DE FUNÇÃO (Rubrica 83185)
O fluxo atual usa designação, afastamentos do titular e impedimentos do substituto, segmentação por competência/vigência, composição e opção remuneratória conferidas e conciliação de pagamentos. PDFs são opcionais e os documentos do mesmo processo são agrupados. O contrato agregado descrito abaixo é legado. Consulte [Substituição por períodos](../docs/substituicao-periodos.md) para o contrato atual, memória e limites.
* [cite_start]**Regra de Negócio:** Destina-se a calcular a compensação pecuniária retroativa devida ao servidor que assume temporariamente uma função de maior hierarquia[cite: 19, 32]. O valor do pagamento é proporcional aos dias de efetiva substituição.
* **Fórmula:** Diferença Mensal = Valor(Função Substituta) - Valor(Função Própria)
  Valor Devido = (Diferença Mensal / Dias do Mês) * Dias Substituídos
  Dias Substituídos = Dias do período - Dias de férias concomitantes (`Interrupção`)

### FLUXO 2: ADICIONAL DE INSALUBRIDADE E PERICULOSIDADE RETROATIVO
* **Regra de Negócio:** Mapeamento de parcelas retroativas de adicionais ocupacionais. [cite_start]Aplica-se sobre o valor mensal de direito as bonificações temporais (como reflexos de férias e 13º salário)[cite: 22, 32].
* **Fórmula:** Valor Total = Somatório de (Valor Base do Mês * Multiplicador do Período)
  *Onde o multiplicador é 1.5 em meses de férias e 2.0 em meses com 13º salário.*

### FLUXO 3: ABONO DE PERMANÊNCIA RETROATIVO
O fluxo atual separa direito confirmado, contribuição descontada e pagamentos por parcela regular/13º. Usa observações de 98002 e 98004 sem inferir elegibilidade, com revisão de acertos e cobertura. O contrato anual abaixo é legado e representa apenas soma informada. Consulte [Abono por parcelas](../docs/abono-parcelas.md).
* [cite_start]**Regra de Negócio:** Reembolso da contribuição previdenciária (PSS) efetuada pelo servidor que, tendo completado os requisitos para aposentadoria voluntária, opta por permanecer em atividade[cite: 32].
* **Fórmula:**
  Total Acumulado = Somatório de todos os valores mensais de PSS retidos no período retroativo.

### FLUXO 4: RESCISÃO DE CONTRATO DE PROFESSOR SUBSTITUTO
O fluxo atual utiliza datas explícitas, sugestões revisáveis e pagamentos associados a períodos/base; apresenta **saldo das parcelas calculadas**, mantendo o alias legado da API. Consulte [Rescisão por períodos](../docs/rescisao-periodos.md). O contrato agregado abaixo é preservado por compatibilidade; valores acima de 24 avos exigem regra no novo contrato, sem truncamento silencioso.
* **Regra de Negócio:** Aplica-se ao desligamento de professores contratados temporariamente. [cite_start]Consolida o pagamento de saldo salarial proporcional, férias indenizadas e décimo terceiro salário proporcional[cite: 22].
* **Fórmulas por Rubrica:**
  1. Saldo de Salário (Ref 742) = Salário Mensal * (Dias Trabalhados / Dias Reais do Mês)
  2. Base do Saldo de Férias = (Salário Mensal / 12) * Saldo de Avos (Teto positivo de 24 meses); Férias Indenizadas (Ref 772) = máximo entre zero e essa base
  3. 1/3 de Férias (Ref 82696) = Base do Saldo de Férias / 3, incluindo saldo negativo para devolução do adicional
  4. 13º Proporcional (Ref 82407) = (Salário Mensal / 12) * Meses de 13º

* **Saldo salarial:** usar a data de rescisão/término para determinar os dias devidos no último mês e comparar com a rubrica salarial da ficha financeira. O recebimento do mês cheio gera diferença negativa a devolver.
* **Férias não gozadas:** contam-se os meses completos a partir do dia de entrada em exercício; a fração final de 15 dias ou mais vale um avo. Cada competência com pagamento regular positivo da rubrica `750 - FERIAS - ADICIONAL 1/3 CDT` desconta 12 avos; sequências auxiliares, descontos e repetições da mesma competência não contam como novos pagamentos. Colunas ou valores ambíguos exigem conferência manual. Com 20 avos adquiridos e duas ocorrências pagas, o saldo é de -4 avos: não há principal indenizável, e devolvem-se apenas `4/12` do adicional de um terço. Para salário de R$ 6.000,00, a devolução é R$ 666,67.

### FLUXO 5: PROGRESSÃO DE CARREIRA DE DOCENTE
* [cite_start]**Regra de Negócio:** Cálculo da diferença financeira resultante do reposicionamento de classe/nível de professores do magistério superior, gerando reflexos sobre o vencimento básico, anuênios e adicionais[cite: 23, 32].
* **Fórmula:**
  Diferença Mensal Total = Diferença Base + Diferença Anuênio + Diferença Insalubridade
  Total Devido = Diferença Mensal Total * (Meses Inteiros + (Dias Proporcionais / Dias do Mês))

Para técnico-administrativos, a diferença mensal inclui também o Incentivo à Qualificação:

* `IQ anterior = VB anterior × percentual anterior de IQ`
* `IQ novo = VB novo × percentual novo de IQ`
* `Diferença de IQ = IQ novo - IQ anterior`
* `Diferença mensal = diferença de VB + diferença de IQ + diferença de anuênio + diferença de insalubridade`

A proporção por dias usa a quantidade real de dias do mês, inclusive 29 dias em fevereiro de ano bissexto. O resultado apresenta separadamente o principal acumulado, o reflexo de férias (`diferença mensal ÷ 3`), o reflexo de 13º e o total com reflexos. As quantidades de reflexos podem ser ajustadas conforme o período efetivamente abrangido.

### FLUXO 6: CONSOLIDAÇÃO DE EXERCÍCIOS ANTERIORES
* [cite_start]**Regra de Negócio:** Uma contabilidade em formato de livro-caixa para consolidar e auditar os montantes de diferenças salariais devidas por anos fiscais já fechados[cite: 23, 27].
* **Fórmula:**
  Total a Receber = Somatório Mensal de (Valor Devido Histórico - Valor Recebido Histórico + Abonos de Férias Retroativos + 13º Retroativo)

---

## 4. DIRETRIZES DE SEGURANÇA, COMPLIANCE (LGPD) E BANCO DE DADOS

Para manter a integridade operacional e adequação legal da Superintendência, o sistema deve aderir às seguintes diretrizes:

### I. Criptografia e Proteção de Dados Sensíveis (LGPD)
* [cite_start]**Proteção de Dados:** Atributos sensíveis de identificação dos funcionários devem receber camadas de segurança e criptografia para proteção contra vazamentos[cite: 25, 28].
* [cite_start]**Termos de Responsabilidade:** Implementação de gestão de termos de responsabilidade (elaboração e oficialização) para os operadores do sistema[cite: 28].

### II. Camada Transicional de Validação (React - "Human-in-the-Loop")
* [cite_start]O sistema apresentará os dados extraídos automaticamente dos documentos em uma interface editável[cite: 19, 30]. [cite_start]O funcionário de RH revisará e ajustará as informações antes de rodar o motor de cálculo definitivo[cite: 19, 30, 38].

### III. Logs e Rastreabilidade de Auditoria
* [cite_start]**Auditabilidade:** Inclusão compulsória de logs de auditoria em todas as operações de processamento para garantir o rastreio completo de qualquer ação ou alteração manual de dados[cite: 27].
* [cite_start]**Controle de Acesso (RBAC):** Sistema de permissões hierárquicas, impedindo que usuários com perfil 'Funcionário' realizem ações críticas restritas ao 'Administrador'[cite: 31].

---

## 5. CONCLUSÃO E APROVAÇÃO TÉCNICA

[cite_start]A validação do MVP junto à SGP/Secretaria de Gestão de Pessoas basear-se-á na confrontação direta das bases matemáticas aqui descritas[cite: 38]. [cite_start]Os testes unitários criados no backend em Python devem cobrir todo o fluxo de execução desde o início antes da homologação final do software[cite: 36, 38].

## Fontes oficiais no cadastro

A gestão salarial permite importar CSV/XLSX/ODS para prévia editável, com origem oficial, obtenção, página/aba, vigência e revisão. A ativação exige conferência explícita do RH; publicação não define efeitos financeiros. A reimportação informa duplicidades/conflitos, preservando referências confirmadas. CD/FG/FCC mantêm componentes separados. A cobertura considera intervalos anteriores a 2020 e mostra lacunas por posição/componente. Consulte [o contrato de importação](../docs/importacao-fontes-oficiais.md). Não há novo upload obrigatório na execução de cálculos.
