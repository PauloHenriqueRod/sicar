# Fontes dos relatórios

Noto Sans Regular, Bold e Italic são distribuídas sem modificações sob a
SIL Open Font License 1.1, reproduzida em `OFL.txt`.

Origem oficial fixada no commit
[`ffebf8c1ee449e544955a7e813c54f9b73848eac`](https://github.com/notofonts/noto-fonts/tree/ffebf8c1ee449e544955a7e813c54f9b73848eac/hinted/ttf/NotoSans).

Essas fontes cobrem português, pontuação Unicode, latim estendido, grego e
cirílico. São carregadas por caminho relativo ao código, independentemente do
diretório de execução e das fontes instaladas no sistema operacional. O fpdf2
embute no PDF apenas os glifos utilizados.

Caracteres fora dessa cobertura interrompem a exportação com
`UnsupportedPDFCharacterError` antes de criar o PDF. O chamador deve apresentar
uma mensagem de validação; nunca substituir ou descartar silenciosamente parte
de nomes e descrições. Para adicionar outros sistemas de escrita, distribua uma
fonte compatível com licença e acrescente testes de extração e renderização.

SHA-256 dos arquivos recebidos:

| Arquivo | SHA-256 |
| --- | --- |
| NotoSans-Regular.ttf | `b85c38ecea8a7cfb39c24e395a4007474fa5a4fc864f6ee33309eb4948d232d5` |
| NotoSans-Bold.ttf | `c976e4b1b99edc88775377fcc21692ca4bfa46b6d6ca6522bfda505b28ff9d6a` |
| NotoSans-Italic.ttf | `36cff144df01309dab648bea71baff9bb074026914afe63aeacc8bc90b67a28b` |

O gerador depende de `fpdf2`, substituto mantido do antigo `fpdf`. Em ambientes
existentes, execute `python -m pip uninstall fpdf` antes de instalar os novos
requisitos: os dois pacotes compartilham o módulo Python `fpdf` e não devem
coexistir.
