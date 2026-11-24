import os

from fpdf import FPDF
from fpdf.enums import XPos, YPos


class PDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 15)
        self.cell(0, 10, 'Superintendencia de Recursos Humanos', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(5)

def gerar_substituicao():
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 10, 'Demonstrativo de Substituicao de Funcao', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
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
    
    return pdf

def gerar_insalubridade():
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 10, 'Retroativo de Insalubridade', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    
    pdf.set_font("Helvetica", '', 12)
    pdf.cell(0, 10, "Historico Mensal:", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    meses = [
        ("JANEIRO E FERIAS", "1500.00"),
        ("FEVEREIRO", "1500.00"),
        ("OUTUBRO", "1500.00"),
        ("NOVEMBRO E 13", "1500.00")
    ]
    for mes, val in meses:
        pdf.cell(0, 10, f"Mes: {mes} | Valor Base: R$ {val}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return pdf

def gerar_abono():
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 10, 'Abono de Permanencia', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    
    pdf.set_font("Helvetica", '', 12)
    anos = [
        ("2023", ["100.50", "200.75", "150.00"]),
        ("2024", ["300.00", "50.00"])
    ]
    for ano, vals in anos:
        vals_str = ", ".join([f"R$ {v}" for v in vals])
        pdf.cell(0, 10, f"Ano: {ano} | Valores: {vals_str}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return pdf

def gerar_rescisao():
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 10, 'Rescisao de Substituto', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    
    dados = [
        ("Classe:", "Auxiliar"),
        ("Nivel:", "1"),
        ("Titulacao:", "Mestrado"),
        ("Meses de Ferias:", "1.5"),
        ("Meses 13o:", "6"),
        ("Dias Trabalhados:", "15"),
        ("Recebido 742_salario:", "R$ 1500.00"),
        ("Recebido 772_ferias:", "R$ 500.00")
    ]
    for chave, valor in dados:
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(50, 10, chave, border=0)
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, 10, valor, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return pdf

def gerar_progressao():
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 10, 'Progressao Docente', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    
    dados = [
        ("Classe Atual:", "Adjunto"),
        ("Nivel Atual:", "2"),
        ("Titulacao:", "Doutorado"),
        ("Classe Antiga:", "Adjunto"),
        ("Nivel Antigo:", "1"),
        ("Anuenio (%):", "15.0"),
        ("Insalubridade (%):", "10.0"),
        ("Meses de Diferenca:", "5.5")
    ]
    for chave, valor in dados:
        pdf.set_font("Helvetica", 'B', 12)
        pdf.cell(50, 10, chave, border=0)
        pdf.set_font("Helvetica", '', 12)
        pdf.cell(0, 10, valor, border=0, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return pdf

def gerar_exercicio_anterior():
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 10, 'Exercicio Anterior', border=0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    
    pdf.set_font("Helvetica", '', 12)
    linhas = [
        "Periodo: 2023-01 | Devido: R$ 500.00 | Recebido: R$ 200.00 | Abono: R$ 50.00 | 13o: R$ 100.00",
        "Periodo: 2023-02 | Devido: R$ 500.00 | Recebido: R$ 250.00 | Abono: R$ 0.00 | 13o: R$ 0.00"
    ]
    for l in linhas:
        pdf.cell(0, 10, l, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return pdf

if __name__ == "__main__":
    base_dir = os.path.dirname(__file__)
    gerar_substituicao().output(os.path.join(base_dir, "pdf_substituicao.pdf"))
    gerar_insalubridade().output(os.path.join(base_dir, "pdf_insalubridade.pdf"))
    gerar_abono().output(os.path.join(base_dir, "pdf_abono_permanencia.pdf"))
    gerar_rescisao().output(os.path.join(base_dir, "pdf_rescisao.pdf"))
    gerar_progressao().output(os.path.join(base_dir, "pdf_progressao.pdf"))
    gerar_exercicio_anterior().output(os.path.join(base_dir, "pdf_exercicio_anterior.pdf"))
    print("Todos os PDFs foram gerados com sucesso na pasta scripts/")
