import os

from fpdf import FPDF
from fpdf.enums import XPos, YPos


class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 15)
        self.cell(0, 10, 'Superintendencia de Recursos Humanos', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_font('Helvetica', 'I', 12)
        self.cell(0, 10, 'Demonstrativo de Substituicao de Funcao', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(10)

def gerar_pdf():
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)

    dados = [
        ("Nome:", "Maria Joaquina de Oliveira"),
        ("Matricula:", "98765432"),
        ("Salario Substituta:", "R$ 8.543,21"),
        ("Salario Propria:", "R$ 5.123,45"),
        ("Dias Substituidos:", "20"),
        ("Mes:", "11"),
        ("Ano:", "2024")
    ]

    for chave, valor in dados:
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(50, 10, chave, border=0)
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, 10, valor, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    caminho_saida = os.path.join(os.path.dirname(__file__), "documento_rh_generico.pdf")
    pdf.output(caminho_saida)
    print(f"PDF gerado com sucesso em: {caminho_saida}")

if __name__ == "__main__":
    gerar_pdf()
