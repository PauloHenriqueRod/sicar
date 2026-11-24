# Extração opcional de atos e portarias

Os layouts de atos introduzidos pelo leitor `rh_paginas_v3` continuam disponíveis no envelope atual `rh_paginas_v5`, conforme o [contrato de origem e conflitos](extracao-documentos-rh.md) das issues #27/#29. O protocolo HTTP continua na versão 2; versões anteriores do leitor permanecem aceitas nos snapshots. Não há novo anexo obrigatório, reconhecimento automático de direito, OCR ou busca de documentos durante um cálculo. Nenhuma regra citada no ato (inclusive prescrição) é executada pelo leitor.

## Exemplos oficiais analisados

Consulta em 31/10/2026. PDFs obtidos em pasta temporária, com inspeção de texto e renderização; os arquivos e os dados pessoais não integram o repositório. Links e identificadores permitem repetir a análise documental. Os testes utilizam outras pessoas, matrículas, datas e concessões sintéticas.

| Fonte oficial | Estrutura analisada e suporte |
| --- | --- |
| UFPI/SRH, [Portaria 15/2026 — mérito TAE](https://ufpi.br/images/SRH/CDP/Portarias%20progresso/Portaria%20SRH%2015-2026%20-%20Mrito.pdf) | Texto nativo; dispositivo vincula efeitos às datas do anexo. Linhas com matrícula, nome, código de cargo, posição de origem/destino e data. Nomes multilinha são reconstruídos entre as colunas comprovadas; linhas incompletas geram aviso. |
| UFPI/SRH, Portaria 104/2024, no [catálogo de progressão docente](https://ufpi.br/portaria-de-progressao-docente-pdp-srh) — [PDF analisado](https://ufpi.br/arquivos_download/arquivos/SRH/Portarias_Docentes/ACHYLLES_DE_OLIVEIRA_COSTA_JUNIOR.pdf) | Texto nativo; progressão por desempenho, docente/regime, destino após `para MS` e data após `a partir de`. Matrícula da assinatura não identifica o docente. |
| UFPI/SRH, Portaria 943/2022, no mesmo catálogo — [PDF analisado](https://ufpi.br/arquivos_download/arquivos/SRH/Portarias_Docentes/Jo%C3%A3o_Santos_incentivo_funcional.pdf) | Texto nativo; incentivo funcional correspondente à titulação, docente, regime e data expressa. Não transforma titulação em progressão nem define valor de RT. |
| UFPI, Ato da Reitoria 1722/2026, seção de substituição do [catálogo da STI](https://ufpi.br/portarias-sti) — [arquivo vinculado pelo canal oficial](https://drive.google.com/file/d/1Su9oyYxSv2QZRGj-93_8a16_7ThIZY1P/view) | Texto extraível e inspeção visual. Designação para responder por FG, SIAPE do substituto, início/fim e nome da titular. Papéis ficam em blocos distintos. A data ao final do ato é documental; não é publicação. |
| UFDPar, Portarias 466, 452 e 451/2022, no [catálogo oficial](https://ufpi.br/comut?id=35621) | Substituição, incentivo e progressão tabular examinados visualmente. PDFs digitalizados, sem texto utilizável. **Não suportados por estes leitores**; exigem entrada manual. Não se presume equivalência com a UFPI. |

## Dados e limites

`leitores_pdf/portarias.py` reconhece `ATO_UFPI_SUBSTITUICAO`, `PORTARIA_UFPI_DOCENTE` e `PORTARIA_UFPI_TAE` pelo cabeçalho UFPI e dispositivo `RESOLVE:` do layout analisado. Há seletores para designação de FG, mérito TAE, titulação e desempenho docente, inclusive a redação “funcional RETROATIVA”. Quando explícita, a posição de origem vem do texto relativo ao beneficiário. A matrícula do signatário não identifica o servidor.

Documento sem texto recebe `SEM_TEXTO`. Atas, retificações, atos de comissão, vários atos na mesma página e formatos sem leitor ficam para revisão manual. Apenas o anexo tabular TAE admite continuidade entre páginas.

Cada observação preserva bloco, página, localizador e texto observado. O anexo em página posterior referencia também a página do cabeçalho com a data do próprio ato. `papel_documental` distingue servidor, substituto e titular quando explícitos. Vínculo não é deduzido de SIAPE/nome; sua associação permanece manual. Documentos mistos conservam os blocos financeiros/cadastrais reconhecidos fora das páginas dos atos.

`data_documento`, `data_publicacao`, `efeitos_financeiros`, `inicio_designacao` e `fim_designacao` são distintos. Os exemplos analisados não informam publicação comprovada do próprio ato; esse campo permanece ausente. Datas de DOU do preâmbulo, assinatura, impressão do navegador ou referências legais não preenchem publicação nem efeitos. Designação não comprova afastamento do titular ou remuneração. Posição TAE permanece separada de classe/nível docente; títulos e códigos de função não resolvem automaticamente referências salariais.

Ambiguidade mantém `valor=null`, `estado=AMBIGUO` e `candidatos` visíveis. Datas inválidas ficam ilegíveis; período invertido permanece sem valor aplicável. Não se escolhe o primeiro candidato, não se troca início/fim e não se completa data ausente. O usuário pode preencher/corrigir o valor e escolher seu destino; resolução exige justificativa e confirmação. A API verifica o valor final e impede trocar papéis explícitos ou usar data do ato/publicação como efeitos. Código da função designada só pode preencher a função substituída.

O [fluxo de revisão](fluxo-revisao-calculos.md) permite cálculo manual e preserva correções e fontes. No anexo TAE, confira número, ano e órgão contra o ato de origem. Referência divergente, ilegível ou sem dispositivo correspondente encerra a continuidade e gera bloco independente. Uma referência compatível ou continuação sem novo identificador preserva o contexto reconhecido. Linhas incompletas delimitam nomes vizinhos e texto entre linhas permanece ambíguo.

## Verificação

`back-sgp/tests/test_extracao_portarias.py` cobre os exemplos, papéis, datas, anexos multipágina e formatos sem leitor com PDFs sintéticos.
