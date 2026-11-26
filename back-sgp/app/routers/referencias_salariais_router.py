import json
from datetime import date
from decimal import Decimal
from fractions import Fraction

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models.referencias_salariais import (
    EstruturaRemuneratoria,
    PendenciaSalarialLegada,
    ReferenciaSalarial,
    RetribuicaoReferencia,
)
from app.models.user import User
from app.routers.auth_router import log_audit
from app.routers.tabelas_router import require_admin_or_dev
from app.schemas.referencias_salariais import ReferenciaEntrada, VincularLegado
from app.services.apuracao_periodos import moeda
from app.services.auth_service import get_current_user
from app.services.salary_references import (
    pendencia_json,
    referencia_json,
    salvar_referencia,
    vincular_pendencia,
)

router = APIRouter(prefix="/tabelas", tags=["Referências salariais"])


@router.get("/posicoes-docentes", dependencies=[Depends(get_current_user)])
def posicoes_docentes(
    data_referencia: date,
    pagina: int = Query(1, ge=1),
    carreira: str | None = None,
    jornada: str | None = None,
    classe_docente: str | None = None,
    nivel_docente: int | None = Query(None, ge=1, le=1000),
    vencimento_basico: Decimal | None = Query(None, ge=0, le=1000000000000),
    db: Session = Depends(get_db),
):
    """Opções de enquadramento com VB e RT confirmados na data da apuração."""
    query = (
        db.query(EstruturaRemuneratoria, RetribuicaoReferencia, ReferenciaSalarial)
        .join(ReferenciaSalarial, ReferenciaSalarial.estrutura_id == EstruturaRemuneratoria.id)
        .join(RetribuicaoReferencia, RetribuicaoReferencia.referencia_id == ReferenciaSalarial.id)
        .filter(
            EstruturaRemuneratoria.carreira.in_(("MAGISTERIO_SUPERIOR", "EBTT")),
            ReferenciaSalarial.estado == "CONFIRMADA",
            ReferenciaSalarial.inicio_vigencia <= data_referencia,
            ReferenciaSalarial.fim_vigencia.is_(None) | (ReferenciaSalarial.fim_vigencia >= data_referencia),
        )
    )
    for column, value in (
        (EstruturaRemuneratoria.carreira, carreira),
        (EstruturaRemuneratoria.jornada, jornada),
        (EstruturaRemuneratoria.classe_docente, classe_docente),
        (EstruturaRemuneratoria.nivel_docente, nivel_docente),
        (ReferenciaSalarial.vencimento_basico, vencimento_basico),
    ):
        if value is not None:
            query = query.filter(column == value)
    rows = query.order_by(EstruturaRemuneratoria.chave, RetribuicaoReferencia.titulacao_chave, RetribuicaoReferencia.id)
    return {
        "total": query.count(),
        "tamanho_pagina": 50,
        "itens": [
            {
                "id": rt.id,
                "titulacao": rt.titulacao,
                "vb": moeda(Fraction(ref.vencimento_basico)),
                "rt": moeda(Fraction(rt.valor)),
                "fonte": ref.fonte,
                "posicao": {
                    "carreira": pos.carreira, "vinculo": pos.vinculo, "jornada": pos.jornada,
                    "versao_carreira": pos.versao_carreira, "classe_docente": pos.classe_docente,
                    "nivel_docente": pos.nivel_docente,
                },
            }
            for pos, rt, ref in rows.offset((pagina - 1) * 50).limit(50).all()
        ],
    }


@router.get("/referencias")
def listar_referencias(
    carreira: str | None = None,
    jornada: str | None = None,
    estado: str | None = None,
    data_referencia: date | None = None,
    pagina: int = Query(1, ge=1),
    tamanho_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    query = db.query(ReferenciaSalarial).join(EstruturaRemuneratoria)
    if carreira:
        query = query.filter(EstruturaRemuneratoria.carreira == carreira)
    if jornada:
        query = query.filter(EstruturaRemuneratoria.jornada == jornada)
    if estado:
        query = query.filter(ReferenciaSalarial.estado == estado)
    if data_referencia:
        query = query.filter(
            ReferenciaSalarial.inicio_vigencia <= data_referencia,
            (ReferenciaSalarial.fim_vigencia.is_(None))
            | (ReferenciaSalarial.fim_vigencia >= data_referencia),
        )
    total = query.count()
    items = (
        query.options(
            joinedload(ReferenciaSalarial.estrutura),
            joinedload(ReferenciaSalarial.retribuicoes),
        )
        .populate_existing()
        .order_by(
            ReferenciaSalarial.inicio_vigencia.desc(), ReferenciaSalarial.id.desc()
        )
        .offset((pagina - 1) * tamanho_pagina)
        .limit(tamanho_pagina)
        .all()
    )
    return {
        "itens": [referencia_json(item) for item in items],
        "total": total,
        "pagina": pagina,
        "tamanho_pagina": tamanho_pagina,
    }


def _gravar(db, dados, user, request, item=None):
    try:
        saved = salvar_referencia(db, dados, user.id, item=item)
        result = referencia_json(saved)
        log_audit(
            db,
            "REFERENCIA_SALARIAL_SALVA",
            f"Referência: {saved.id}; estado: {saved.estado}",
            user.id,
            request.client.host if request.client else None,
        )
        return result
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Conflito de estrutura, titulação ou vigência salarial. Atualize a listagem e confira os intervalos.",
        ) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def dados_exatos(request: Request, dados: ReferenciaEntrada):
    # FastAPI publica/valida o contrato; a segunda leitura preserva a fração JSON.
    try:
        return ReferenciaEntrada.model_validate(
            json.loads(await request.body(), parse_float=Decimal)
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["body", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()[:100]
            ],
        ) from exc


@router.post("/referencias")
def criar_referencia(
    request: Request,
    dados: ReferenciaEntrada = Depends(dados_exatos),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    return _gravar(db, dados, user, request)


@router.put("/referencias/{item_id}")
def atualizar_referencia(
    item_id: int,
    request: Request,
    dados: ReferenciaEntrada = Depends(dados_exatos),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    item = db.query(ReferenciaSalarial).filter_by(id=item_id).with_for_update().first()
    if item is None:
        raise HTTPException(status_code=404, detail="Referência não encontrada.")
    return _gravar(db, dados, user, request, item)


@router.get("/pendencias-legadas")
def listar_pendencias(
    pagina: int = Query(1, ge=1),
    tamanho_pagina: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    query = db.query(PendenciaSalarialLegada)
    return {
        "itens": [
            pendencia_json(item)
            for item in query.order_by(PendenciaSalarialLegada.id)
            .offset((pagina - 1) * tamanho_pagina)
            .limit(tamanho_pagina)
        ],
        "total": query.count(),
        "pagina": pagina,
        "tamanho_pagina": tamanho_pagina,
    }


@router.put("/pendencias-legadas/{item_id}/vinculo")
def vincular_legado(
    item_id: int,
    dados: VincularLegado,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    # Mesma ordem da edição: referência antes da pendência. Impede vincular
    # dados antigos enquanto outra transação modifica a referência confirmada.
    referencia = (
        db.query(ReferenciaSalarial)
        .filter_by(id=dados.referencia_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    pending = (
        db.query(PendenciaSalarialLegada)
        .filter_by(id=item_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if pending is None or referencia is None:
        raise HTTPException(
            status_code=404, detail="Pendência ou referência não encontrada."
        )
    try:
        vincular_pendencia(db, pending, referencia)
        result = pendencia_json(pending)
        log_audit(
            db,
            "LEGADO_SALARIAL_CONFERIDO",
            f"Pendência: {pending.id}; referência: {referencia.id}",
            user.id,
            request.client.host if request.client else None,
        )
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
