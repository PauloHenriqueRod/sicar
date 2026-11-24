# Interface do SICAR

## Fluxo e organização

O RH trabalha com um servidor e vínculo por cálculo. Apresente a modalidade, as seções de anexos opcionais, a revisão e o resultado nessa ordem. Mostre o estado de cada arquivo e mantenha à vista os valores que exigem conferência. Fontes, justificativas e detalhes de leitura podem ficar em seções expansíveis. Veja o [fluxo de revisão](fluxo-revisao-calculos.md).

Nas consultas e telas de gestão, use `PagePanel` para título, ações e mensagens, seguido por filtros (`FilterBar`), resultados (`TableViewport`) e paginação. Em telas estreitas, restrinja a rolagem horizontal à tabela e preserve rótulos, ações e ordem de leitura.

## Cores, texto e acessibilidade

- Use os tokens de [index.css](../front-sgp/src/index.css) nos dois temas. Fundos e painéis são neutros. Azul identifica a ação principal, links e seleção. Verde indica sucesso, vermelho indica erro, âmbar indica atenção e cinza indica pendência. Acompanhe o estado com texto ou ícone identificável.
- Use a família sem serifa do sistema, corpo de 16 px, rótulos de 14 px e controles de 2,75 rem. Reserve maior peso para títulos e totais. Preserve o foco visível, a operação por teclado e a preferência por movimento reduzido.
- O [teste de contraste](../front-sgp/src/utils/colorContrast.test.ts) verifica os pares dos temas claro e escuro. As metas são 4,5:1 para texto e 3:1 para contornos e foco. [Contraste de texto](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum) e [de componentes](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast).

## Controles compartilhados

| Componente | Comportamento esperado |
| --- | --- |
| `Button` | Use `primary` para a ação principal, `secondary` para apoio, `quiet` para ação discreta e `link` para navegação. Dê nome acessível a `icon`. O tipo padrão é `button`. Declare `submit` para envio e use `busy` para anunciar processamento e impedir repetição. |
| `TextField` e `SelectField` | Mantenha o rótulo visível. Associe dicas e erros ao campo. Reserve o placeholder para exemplos. |
| `Modal` | Ao abrir, leve o foco para dentro e mantenha-o ali durante a interação. Ao fechar, devolva-o ao acionador. Escape fecha a janela em repouso. Clique no fundo preserva o formulário e o processamento bloqueia o fechamento. |
| `Pagination` e `ContentTabs` | Identifique a página ou aba ativa, mantenha a navegação por teclado e desabilite controles nos limites. Oculte a paginação quando houver uma única página. |
| `SectionHeader` e `ActionFeedback` | Agrupe título e ações. Informe o resultado e, em caso de falha, como prosseguir. Diferencie lista vazia, filtros sem resultados, erro de consulta e sucesso parcial. |

Reutilize os [componentes compartilhados](../front-sgp/src/components/ui/index.ts). Valide mudanças com lint, build e testes do frontend, além de conferir teclado, temas e larguras de tela.

## Vocabulário e apresentação dos dados

Use português brasileiro, frases curtas e verbos que indiquem a ação, como “Calcular” e “Baixar PDF”. Preserve termos que permitem localizar um dado na ficha, como “Matrícula SIAPE” e “T. serv.”. Os nomes de páginas, cálculos e perfis e os formatadores ficam em [presentation.ts](../front-sgp/src/utils/presentation.ts).

Exiba moeda como `R$ 1.234,56`, datas como `DD/MM/AAAA` e horas no formato de 24 horas. Preserve identificadores como texto. Diferencie zero confirmado (`R$ 0,00`), campo ausente (“Não informado”) e total histórico ilegível (“Não disponível”). A formatação de tela preserva a precisão utilizada pelo motor.

## Referências de design

As diretrizes de serviços públicos consultadas em 07/10/2026 orientaram a escolha de padrões familiares e de ajuda junto ao campo que o RH está conferindo. A avaliação da usabilidade requer observar o uso do sistema. [Princípios do USWDS](https://designsystem.digital.gov/design-principles/), [padrões do GOV.UK](https://design-system.service.gov.uk/get-started/) e [orientações do Home Office](https://design.homeoffice.gov.uk/design-system/patterns/help-users-to/get-more-details).
