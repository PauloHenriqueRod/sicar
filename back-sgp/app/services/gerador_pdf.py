import os
import tempfile
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from pathlib import Path
from typing import Any

from fpdf import FPDF
from fpdf.enums import MethodReturnValue, XPos, YPos

from app.services.pdf_report_limits import (
    MAX_REPORT_FILE_BYTES,
    MAX_REPORT_PAGES,
    PDFReportLimitError,
    UnsupportedPDFCharacterError,
    encode_report_payload,
)

FONT_FAMILY = "NotoSans"
FONT_DIRECTORY = Path(__file__).resolve().parents[1] / "assets" / "fonts"


class RelatorioOficialPDF(FPDF):
    def __init__(self):
        super().__init__()
        # Fontes livres empacotadas: a exportacao nao depende das fontes do SO
        # nem substitui caracteres Unicode por '?' ou remove acentos.
        for style, filename in (("", "Regular"), ("B", "Bold"), ("I", "Italic")):
            self.add_font(FONT_FAMILY, style, FONT_DIRECTORY / f"NotoSans-{filename}.ttf")

    def add_page(self, *args, **kwargs):
        if self.page_no() >= MAX_REPORT_PAGES:
            raise PDFReportLimitError("O relatório excede o limite de páginas.")
        return super().add_page(*args, **kwargs)

    def validate_characters(self, value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                self.validate_characters(key)
                self.validate_characters(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.validate_characters(item)
        else:
            supported = self.fonts[FONT_FAMILY.lower()].cmap
            missing = sorted({ord(character) for character in str(value)
                              if character not in "\n\r\t" and ord(character) not in supported})
            if missing:
                codes = ", ".join(f"U+{code:04X}" for code in missing[:8])
                raise UnsupportedPDFCharacterError(
                    f"O relatório contém caracteres sem suporte na fonte ({codes}). "
                    "Revise esses caracteres ou solicite uma fonte compatível antes de exportar."
                )

    def header(self):
        self.set_text_color(0, 0, 0)
        self.set_font(FONT_FAMILY, 'B', 15)
        self.cell(0, 8, 'República Federativa do Brasil', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.set_font(FONT_FAMILY, 'B', 12)
        self.set_text_color(50, 50, 50)
        self.cell(0, 6, 'SICAR — Sistema de Conferência e Apuração Remuneratória', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.set_font(FONT_FAMILY, '', 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, 'Relatório Analítico Oficial de Processamento', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.line(10, 35, 200, 35)
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font(FONT_FAMILY, 'I', 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, 'Documento gerado eletronicamente. Confira os dados com as fontes do processo.', new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')

class GeradorPDF:
    @staticmethod
    def gerar_relatorio(tipo_calculo: str, dados_extraidos: dict[str, Any], resultado_calculo: dict[str, Any],
                        *, output_path: str | None = None) -> str:
        encode_report_payload(tipo_calculo, dados_extraidos, resultado_calculo)
        pdf = RelatorioOficialPDF()
        # Valida antes de criar o temporario; nunca disponibiliza PDF incompleto.
        pdf.validate_characters((tipo_calculo, dados_extraidos, resultado_calculo))
        
        # Remoção estrita de metadados para evitar Data Leakage
        pdf.set_author('')
        pdf.set_creator('')
        pdf.set_title('')
        pdf.set_subject('')
        pdf.set_keywords('')
        
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)
        
        # Metadata
        pdf.set_font(FONT_FAMILY, 'B', 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(50, 6, "Tipo de Processamento:", border=1)
        pdf.set_font(FONT_FAMILY, '', 10)
        pdf.cell(140, 6, str(tipo_calculo).replace('_', ' ').upper(), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.set_font(FONT_FAMILY, 'B', 10)
        pdf.cell(50, 6, "Data de Emissão:", border=1)
        pdf.set_font(FONT_FAMILY, '', 10)
        pdf.cell(140, 6, datetime.now().strftime("%d/%m/%Y as %H:%M:%S"), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        pdf.set_font(FONT_FAMILY, 'B', 10)
        pdf.cell(50, 6, "Matrícula Vinculada:", border=1)
        pdf.set_font(FONT_FAMILY, '', 10)
        pdf.cell(140, 6, str(dados_extraidos.get('matricula', 'N/A')), border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        
        pdf.ln(5)

        # Dados Extraídos
        pdf.set_font(FONT_FAMILY, 'B', 12)
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(0, 8, " 1. Parâmetros de Entrada (Extrato Base)", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        pdf.set_font(FONT_FAMILY, '', 10)
        
        def imprimir_valor(chave: str, valor: Any, nivel: int = 0):
            largura = 190 - min(nivel * 5, 30)
            margem = 10 + 190 - largura
            rotulo = str(chave).replace('_', ' ').capitalize()
            pdf.set_x(margem)
            if isinstance(valor, (dict, list)):
                if pdf.get_y() + 23 > pdf.page_break_trigger:
                    pdf.add_page()
                    pdf.set_x(margem)
                pdf.set_font(FONT_FAMILY, 'B', 10)
                pdf.multi_cell(largura, 6, rotulo, border=1, fill=True, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                registros = valor.items() if isinstance(valor, dict) else (
                    (f"Registro {indice + 1}", item) for indice, item in enumerate(valor)
                )
                for subchave, subvalor in registros:
                    imprimir_valor(str(subchave), subvalor, nivel + 1)
                return
            pdf.set_font(FONT_FAMILY, 'B', 9)
            linhas_rotulo = pdf.multi_cell(largura, 5, rotulo, dry_run=True, output=MethodReturnValue.LINES)
            pdf.set_font(FONT_FAMILY, '', 10)
            contador = chave.endswith("_id") or chave.startswith(("exercicio", "dias_", "meses_", "ano", "percentual_", "quantidade_", "avos_")) or chave in {"multiplicador", "id", "versao_snapshot", "referencia_id", "nivel_docente", "padrao_tae", "nivel", "avos", "segmento_base"}
            if isinstance(valor, (float, int)) and not isinstance(valor, bool) and not contador:
                # A apresentação segue a regra monetária sem alterar os valores do histórico.
                decimal_value = Decimal(str(valor))
                with localcontext() as context:
                    context.prec = max(64, decimal_value.adjusted() + 4)
                    apresentado = decimal_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                valor_str = f"R$ {apresentado:.2f}"
            elif tipo_calculo in {"apuracao_periodos", "progressao", "insalubridade", "substituicao", "rescisao", "abono", "exercicio_anterior"} and chave in {"principal", "acrescimos", "reducoes", "devido", "recebido", "saldo", "total_geral_a_receber", "saldo_parcelas_calculadas", "devolucao", "valor_conciliado", "contribuicao_conciliada"} and isinstance(valor, str):
                valor_str = f"R$ {valor}"
            else:
                valor_str = str(valor)
            linhas_valor = pdf.multi_cell(largura, 6, valor_str, dry_run=True, output=MethodReturnValue.LINES)
            altura = len(linhas_rotulo) * 5 + len(linhas_valor) * 6
            if pdf.get_y() + altura > pdf.page_break_trigger and altura < pdf.page_break_trigger - 44:
                pdf.add_page()
            pdf.set_x(margem)
            pdf.set_font(FONT_FAMILY, 'B', 9)
            pdf.multi_cell(largura, 5, rotulo, border="LTR", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_x(margem)
            pdf.set_font(FONT_FAMILY, '', 10)
            pdf.multi_cell(largura, 6, valor_str, border="LBR", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        for k, v in dados_extraidos.items():
            if k != "resultado_calculo":
                imprimir_valor(k, v)

        pdf.ln(5)

        # Resultados
        pdf.set_font(FONT_FAMILY, 'B', 12)
        pdf.cell(0, 8, " 2. Detalhamento de Rubricas e Cálculos", border=1, new_x=XPos.LMARGIN, new_y=YPos.NEXT, fill=True)
        
        resultado = resultado_calculo.get("resultado_calculo", resultado_calculo)
        for k, v in resultado.items():
            if k in {"total_liquido_a_receber", "total_geral", "total_geral_a_receber"} and "saldo_parcelas_calculadas" in resultado:
                continue
            imprimir_valor(str(k), v)

        # Arquivo temporário
        if output_path is None:
            fd, temp_path = tempfile.mkstemp(suffix=".pdf")
            os.close(fd)
        else:
            # O processo supervisor fornece um caminho reservado por ele; nunca vem da API.
            temp_path = output_path
        try:
            pdf.output(temp_path)
            if os.path.getsize(temp_path) > MAX_REPORT_FILE_BYTES:
                raise PDFReportLimitError("O relatório excede o limite de tamanho do PDF.")
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
        return temp_path
