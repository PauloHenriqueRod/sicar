"""Revisão explícita, ativação aditiva e cobertura histórica de fontes oficiais."""

import json
from collections import defaultdict
from datetime import date, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.fontes_oficiais import (
    EstruturaFuncao,
    EstruturaIQ,
    ImportacaoFonte,
    LinhaImportacaoFonte,
    ReferenciaFuncao,
    ReferenciaIQ,
)
from app.models.referencias_salariais import (
    EstruturaRemuneratoria,
    ReferenciaSalarial,
    RetribuicaoReferencia,
)
from app.schemas.fontes_oficiais import LinhaFuncao, LinhaIQ, LinhaSalarial
from app.schemas.referencias_salariais import PosicaoSalarial, ReferenciaEntrada
from app.services.salary_references import salvar_referencia
from app.utils.clock import utcnow
from app.utils.salary_keys import salary_key

TERMINAL = {"ATIVADA", "DUPLICADA"}


def validate_line(data):
    try:
        model = {"FUNCAO": LinhaFuncao, "IQ": LinhaIQ}.get(data.get("tipo"), LinhaSalarial)
        return model.model_validate(data), []
    except ValidationError as exc:
        return None, [
            ".".join(map(str, error["loc"])) + ": " + error["msg"]
            for error in exc.errors()[:25]
        ]


def line_json(row):
    return {
        "id": row.id,
        "localizador": row.localizador,
        "original": json.loads(row.original_json),
        "dados": json.loads(row.dados_json),
        "problemas": json.loads(row.problemas_json),
        "estado": row.estado,
        "versao": row.versao,
        "referencia_id": row.referencia_id,
        "funcao_id": row.funcao_id,
        "revisado_por": row.revisado_por,
        "revisado_em": row.revisado_em.isoformat() if row.revisado_em else None,
    }


def source_json(db, batch):
    rows = (
        db.query(LinhaImportacaoFonte)
        .filter_by(lote_id=batch.id)
        .order_by(LinhaImportacaoFonte.id)
        .all()
    )
    return {
        "id": batch.id,
        "titulo": batch.titulo,
        "url": batch.url,
        "obtido_em": batch.obtido_em.isoformat(),
        "publicado_em": batch.publicado_em.isoformat() if batch.publicado_em else None,
        "arquivo": batch.arquivo,
        "sha256": batch.sha256,
        "formato": batch.formato,
        "linhas": [line_json(row) for row in rows],
        "rejeicoes": [
            line_json(row) for row in rows if row.estado in ("REJEITADA", "CONFLITO")
        ],
        "resumo": {
            state: sum(row.estado == state for row in rows)
            for state in ("PENDENTE", "REJEITADA", "CONFLITO", "ATIVADA", "DUPLICADA")
        },
    }


def create_preview(db, origin, filename, digest, rows, user_id):
    batch = ImportacaoFonte(
        **origin.model_dump(include={"titulo", "url", "obtido_em", "publicado_em"}),
        arquivo=filename[:200],
        sha256=digest,
        formato=filename.rsplit(".", 1)[-1].upper()[:20],
        criado_por=user_id,
        criado_em=utcnow(),
    )
    db.add(batch)
    db.flush()
    for item in rows:
        data = item["dados"]
        _, errors = validate_line(data)
        if item.get("erro"):
            errors.insert(0, item["erro"])
        db.add(
            LinhaImportacaoFonte(
                lote_id=batch.id,
                localizador=item["localizador"][:200],
                original_json=json.dumps(
                    {**item.get("original", data), "_localizador": item["localizador"]},
                    ensure_ascii=False,
                ),
                dados_json=json.dumps(data, ensure_ascii=False),
                problemas_json=json.dumps(errors, ensure_ascii=False),
                estado="REJEITADA" if errors else "PENDENTE",
                versao=1,
            )
        )
    db.flush()
    return batch


def group_key(candidate):
    position = candidate.chave_estrutura()
    return (
        "FUNCAO" if isinstance(candidate, LinhaFuncao) else "IQ" if isinstance(candidate, LinhaIQ) else "SALARIO",
        position,
        candidate.inicio_vigencia,
        candidate.fim_vigencia,
    )


def _overlap(query, model, candidate):
    query = query.filter(
        or_(
            model.fim_vigencia.is_(None),
            model.fim_vigencia >= candidate.inicio_vigencia,
        )
    )
    if candidate.fim_vigencia is not None:
        query = query.filter(model.inicio_vigencia <= candidate.fim_vigencia)
    return query


def _activate_salary(db, records, source, user_id):
    first = records[0]
    basic = {row.valor for row in records if row.tipo == "VB"}
    rt = {}
    for row in records:
        if row.tipo == "RT":
            title = salary_key(row.titulacao)
            if title in rt and rt[title][1] != row.valor:
                raise ValueError(
                    "RTs divergentes para a mesma titulação/posição/vigência."
                )
            rt[title] = (row.titulacao, row.valor)
    if len(basic) > 1:
        raise ValueError("VBs divergentes para a mesma posição/vigência.")
    existing = (
        _overlap(
            db.query(ReferenciaSalarial)
            .join(EstruturaRemuneratoria)
            .filter(
                EstruturaRemuneratoria.chave == first.chave_estrutura(),
                ReferenciaSalarial.estado == "CONFIRMADA",
            ),
            ReferenciaSalarial,
            first,
        )
        .with_for_update(of=ReferenciaSalarial)
        .populate_existing()
        .all()
    )
    if existing:
        ref = existing[0]
        matching_rt = {r.titulacao_chave: r.valor for r in ref.retribuicoes}
        if (
            len(existing) == 1
            and ref.inicio_vigencia == first.inicio_vigencia
            and ref.fim_vigencia == first.fim_vigencia
            and (not basic or ref.vencimento_basico == next(iter(basic)))
        ):
            if any(
                key in matching_rt and matching_rt[key] != value
                for key, (_, value) in rt.items()
            ):
                raise ValueError(
                    "RT divergente de valor já confirmado. A referência foi preservada."
                )
            missing = {key: pair for key, pair in rt.items() if key not in matching_rt}
            if not missing:
                return "DUPLICADA", ref.id, None
            if len(matching_rt) + len(missing) > 20:
                raise ValueError(
                    "Máximo de 20 titulações por referência. Confira as colunas da fonte."
                )
            # Complemento aditivo: não modifica VB, vigência, fonte do VB ou RTs
            # existentes. A origem e a revisão da RT ficam na linha deste lote.
            for key, (title, value) in missing.items():
                added = RetribuicaoReferencia(
                    titulacao=title, titulacao_chave=key, valor=value
                )
                ref.retribuicoes.append(added)
                db.flush()
                db.refresh(added, attribute_names=["valor"])
                if added.valor != value:
                    raise ValueError(
                        "O banco não preservou a precisão da RT. Confira o original e utilize PostgreSQL."
                    )
            return "ATIVADA", ref.id, None
        raise ValueError(
            "Conflito com referência confirmada. Ela foi preservada; confira posição, valores e vigências."
        )
    if not basic:
        raise ValueError(
            "RT sem VB compatível na prévia. Importe o VB da mesma posição e vigência; nenhum salário é presumido."
        )
    entry = ReferenciaEntrada(
        **first.model_dump(include=set(PosicaoSalarial.model_fields)),
        inicio_vigencia=first.inicio_vigencia,
        fim_vigencia=first.fim_vigencia,
        vencimento_basico=next(iter(basic)),
        retribuicoes=[
            {"titulacao": title, "valor": value} for title, value in rt.values()
        ],
        fonte=source,
        estado="CONFIRMADA",
    )
    ref = salvar_referencia(db, entry, user_id)
    return "ATIVADA", ref.id, None


def _activate_function(db, records, source, user_id):
    first = records[0]
    if len({item.valor for item in records}) != 1:
        raise ValueError(
            "Valores divergentes para o mesmo componente de função e vigência."
        )
    structure = (
        db.query(EstruturaFuncao)
        .filter_by(chave=first.chave_estrutura())
        .with_for_update()
        .first()
    )
    if structure is None:
        structure = EstruturaFuncao(
            chave=first.chave_estrutura(),
            **first.model_dump(
                include={"tipo_funcao", "codigo_funcao", "modalidade", "componente"}
            ),
        )
        db.add(structure)
        db.flush()
    existing = _overlap(
        db.query(ReferenciaFuncao).filter_by(estrutura_id=structure.id),
        ReferenciaFuncao,
        first,
    ).all()
    if existing:
        ref = existing[0]
        if (
            len(existing) == 1
            and ref.inicio_vigencia == first.inicio_vigencia
            and ref.fim_vigencia == first.fim_vigencia
            and ref.valor == first.valor
        ):
            return "DUPLICADA", None, ref.id
        raise ValueError(
            "Conflito com componente de função confirmado. O cadastro existente foi preservado."
        )
    ref = ReferenciaFuncao(
        estrutura_id=structure.id,
        inicio_vigencia=first.inicio_vigencia,
        fim_vigencia=first.fim_vigencia,
        valor=first.valor,
        fonte=source,
        conferido_por=user_id,
        conferido_em=utcnow(),
    )
    db.add(ref)
    db.flush()
    db.refresh(ref, attribute_names=["valor"])
    if ref.valor != first.valor:
        raise ValueError(
            "O banco não preservou a precisão. Confira o valor original e utilize PostgreSQL."
        )
    return "ATIVADA", None, ref.id


def _activate_iq(db, records, source, user_id):
    first = records[0]
    if len({r.valor for r in records}) != 1:
        raise ValueError("Percentuais de IQ divergentes para a mesma titulação/vigência.")
    key = first.chave_estrutura()
    structure = db.query(EstruturaIQ).filter_by(chave=key).first()
    if structure is None:
        structure = EstruturaIQ(chave=key, titulacao=first.titulacao)
        db.add(structure)
        db.flush()
    matches = _overlap(db.query(ReferenciaIQ).filter_by(estrutura_id=structure.id), ReferenciaIQ, first).all()
    if matches:
        if len(matches) == 1 and matches[0].inicio_vigencia == first.inicio_vigencia and matches[0].fim_vigencia == first.fim_vigencia and matches[0].valor == first.valor:
            return "DUPLICADA", None, None
        raise ValueError("Conflito com percentual de IQ confirmado; referência existente preservada.")
    reference = ReferenciaIQ(estrutura_id=structure.id, inicio_vigencia=first.inicio_vigencia,
        fim_vigencia=first.fim_vigencia, valor=first.valor, fonte=source,
        conferido_por=user_id, conferido_em=utcnow())
    db.add(reference)
    db.flush()
    db.refresh(reference, attribute_names=["valor"])
    if reference.valor != first.valor:
        raise ValueError("O banco não preservou a precisão do percentual de IQ.")
    return "ATIVADA", None, None


def activate(db, batch, selection, user_id):
    rows = (
        db.query(LinhaImportacaoFonte)
        .filter_by(lote_id=batch.id)
        .order_by(LinhaImportacaoFonte.id)
        .with_for_update()
        .populate_existing()
        .all()
    )
    wanted = {row.id: row.versao for row in selection.linhas}
    if len(wanted) != len(selection.linhas) or not set(wanted) <= {
        row.id for row in rows
    }:
        raise HTTPException(
            status_code=400, detail="Seleção inválida para esta prévia."
        )
    if any(row.id in wanted and wanted[row.id] != row.versao for row in rows):
        raise HTTPException(
            status_code=409,
            detail="A prévia foi alterada. Atualize e confira novamente antes de ativar.",
        )
    groups = defaultdict(list)
    unselected = set()
    for row in rows:
        candidate, errors = validate_line(json.loads(row.dados_json))
        if row.id not in wanted:
            if candidate is not None and row.estado not in TERMINAL:
                unselected.add(group_key(candidate))
            continue
        if row.estado in TERMINAL:
            continue
        if row.estado == "REJEITADA" or errors or candidate is None:
            row.estado, row.problemas_json = (
                "REJEITADA",
                json.dumps(
                    errors
                    or json.loads(row.problemas_json)
                    or ["Salve a revisão desta linha antes de ativar."],
                    ensure_ascii=False,
                ),
            )
            row.versao += 1
            continue
        groups[group_key(candidate)].append((row, candidate))
    source = f"Importação #{batch.id}: {batch.titulo} — {batch.url}"[:500]
    overlaps = set()
    by_position = defaultdict(list)
    for key in groups:
        by_position[key[:2]].append(key)
    for keys in by_position.values():
        ordered = sorted(keys, key=lambda key: key[2])
        for index, first in enumerate(ordered):
            for second in ordered[index + 1 :]:
                if first[3] is not None and second[2] > first[3]:
                    break
                overlaps.update((first, second))
    for key, items in sorted(
        groups.items(), key=lambda item: (item[0][:3], item[0][3] or date.max)
    ):
        status, reference_id, function_id, errors = "CONFLITO", None, None, []
        try:
            if key in overlaps:
                raise ValueError(
                    "Vigências sobrepostas na prévia para a mesma posição/componente. Confira ambas antes de ativar."
                )
            if key in unselected:
                raise ValueError(
                    "Selecione todas as linhas da mesma posição e vigência para não omitir VB ou RT."
                )
            with db.begin_nested():
                handler = {"FUNCAO": _activate_function, "IQ": _activate_iq}.get(key[0], _activate_salary)
                status, reference_id, function_id = handler(
                    db, [candidate for _, candidate in items], source, user_id
                )
        except IntegrityError:
            errors = [
                "Conflito concorrente ou vigência duplicada. Atualize a prévia; nenhuma referência confirmada foi sobrescrita."
            ]
        except OperationalError as exc:
            if getattr(exc.orig, "pgcode", None) not in {
                "40P01",
                "40001",
                "55P03",
            } and getattr(exc.orig, "sqlite_errorcode", None) not in {5, 6}:
                raise
            errors = [
                "Conflito concorrente de gravação. Atualize a prévia e confira novamente antes de tentar ativar."
            ]
        except ValueError as exc:
            errors = [str(exc)]
        for row, _ in items:
            row.estado, row.referencia_id, row.funcao_id = (
                status,
                reference_id,
                function_id,
            )
            row.problemas_json = json.dumps(errors, ensure_ascii=False)
            row.revisado_por, row.revisado_em = user_id, utcnow()
            row.versao += 1
    db.flush()


def coverage_intervals(intervals, start, end):
    cursor = start
    gaps, covered = [], []
    for left, right in sorted(intervals, key=lambda span: span[0]):
        left, right = max(start, left), min(end, right or end)
        if right < left:
            continue
        covered.append({"inicio": left.isoformat(), "fim": right.isoformat()})
        if left > cursor:
            gaps.append(
                {
                    "inicio": cursor.isoformat(),
                    "fim": (left - timedelta(days=1)).isoformat(),
                }
            )
        if right == date.max:
            return covered, gaps
        cursor = max(cursor, right + timedelta(days=1))
    if cursor <= end:
        gaps.append({"inicio": cursor.isoformat(), "fim": end.isoformat()})
    return covered, gaps
