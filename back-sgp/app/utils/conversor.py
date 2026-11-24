import calendar
import html
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


class ConversorSaneador:
    """Classe utilitária para tratar formatações e dízimas de planilhas brasileiras."""

    @staticmethod
    def sanitizar_texto(texto: Any) -> str:
        """Escapa tags HTML para evitar XSS ao extrair strings do PDF."""
        if not texto:
            return ""
        return html.escape(str(texto).strip())

    @staticmethod
    def obter_dias_do_mes(mes: int, ano: int) -> int:
        """Retorna a quantidade real de dias do mês especificado."""
        if not (1 <= mes <= 12):
            return 30
        return calendar.monthrange(ano, mes)[1]

    @staticmethod
    def para_decimal(valor: Any) -> Decimal:
        """Lê o formato legado sem uma conversão binária intermediária."""
        if valor is None or str(valor).strip() == "" or str(valor).strip() == "0":
            return Decimal(0)
        limpo = str(valor).replace("R$", "").replace(" ", "").strip()
        if "." in limpo and "," in limpo:
            limpo = limpo.replace(".", "").replace(",", ".")
        elif "," in limpo:
            limpo = limpo.replace(",", ".")
        try:
            return Decimal(limpo)
        except InvalidOperation:
            return Decimal(0)

    @staticmethod
    def para_float(valor: Any) -> float:
        return float(ConversorSaneador.para_decimal(valor))

    @staticmethod
    def para_data(valor: Any) -> date | None:
        if not valor:
            return None
        meses_siape = {
            "JAN": "01", "FEV": "02", "MAR": "03", "ABR": "04", "MAI": "05", "JUN": "06",
            "JUL": "07", "AGO": "08", "SET": "09", "OUT": "10", "NOV": "11", "DEZ": "12",
        }
        texto = str(valor).strip().upper()
        for mes, numero in meses_siape.items():
            texto = texto.replace(mes, numero)
        for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d%m%Y"):
            try:
                return datetime.strptime(texto, formato).date()
            except ValueError:
                continue
        return None
