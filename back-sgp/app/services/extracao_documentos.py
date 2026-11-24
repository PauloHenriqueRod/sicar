"""Entrada compatível da extração; despacho por layouts independentes."""
from app.services.leitores_pdf.base import data_documental
from app.services.leitores_pdf.geometria import linhas_posicionadas
from app.services.leitores_pdf.registro import extrair_documento

__all__ = ["data_documental", "extrair_documento", "linhas_posicionadas"]
