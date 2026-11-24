"""Consulta paginada mantendo os identificadores pessoais cifrados no banco."""
from datetime import datetime
from app.models.tabelas_salariais import HistoricoCalculo


def history_page(query, page, size, search, calculation_type, career, title, sort, direction):
    if calculation_type:
        query = query.filter(HistoricoCalculo.tipo_calculo == calculation_type)
    offset = (page - 1) * size
    reverse = direction == "desc"
    if not search.strip() and not career and not title and sort in ("data_calculo", "tipo_calculo"):
        column = getattr(HistoricoCalculo, sort)
        ordering = column.desc() if reverse else column.asc()
        tie = HistoricoCalculo.id.desc() if reverse else HistoricoCalculo.id.asc()
        return query.order_by(ordering, tie).offset(offset).limit(size).all(), query.count()

    # A cifra é aleatória: SQL LIKE/ORDER BY no ciphertext daria resultados incorretos.
    # Consulta só metadados em lotes; snapshots financeiros são lidos apenas para a página.
    metadata = query.with_entities(
        HistoricoCalculo.id, HistoricoCalculo.data_calculo, HistoricoCalculo.tipo_calculo,
        HistoricoCalculo.matricula, HistoricoCalculo.classe, HistoricoCalculo.titulacao,
    ).yield_per(200)
    needle = search.strip().casefold()
    matched = []
    for row in metadata:
        if career and (row.classe or "").casefold() != career.casefold():
            continue
        if title and (row.titulacao or "").casefold() != title.casefold():
            continue
        if needle and needle not in (row.matricula or "").casefold():
            continue
        value = getattr(row, sort)
        key = (value or datetime.min) if sort == "data_calculo" else (value or "").casefold()
        matched.append((key, row.id))
    matched.sort(reverse=reverse)
    ids = [item[1] for item in matched[offset:offset + size]]
    if not ids:
        return [], len(matched)
    records = {record.id: record for record in query.filter(HistoricoCalculo.id.in_(ids)).all()}
    return [records[item] for item in ids], len(matched)
