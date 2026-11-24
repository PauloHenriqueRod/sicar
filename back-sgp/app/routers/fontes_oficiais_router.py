import json
from datetime import date
from hashlib import sha256
from pathlib import PurePosixPath
from threading import BoundedSemaphore
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
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
from app.models.user import User
from app.routers.auth_router import log_audit
from app.routers.tabelas_router import require_admin_or_dev
from app.schemas.fontes_oficiais import (
    AtivarFonte,
    CadastroManual,
    ConfiguracaoFonte,
    ConsultaCobertura,
    EditarLinha,
)
from app.services.official_source_reader import MAX_BYTES, SourceReadError, read_source
from app.services.official_sources import (
    TERMINAL,
    activate,
    coverage_intervals,
    create_preview,
    source_json,
    validate_line,
)
from app.utils.limiter import limiter
from app.utils.salary_keys import salary_key

router = APIRouter(prefix="/tabelas/fontes", tags=["Importação de fontes oficiais"])
preview_slots = BoundedSemaphore(2)
MGI = "https://www.gov.br/servidor/pt-br/observatorio-de-pessoal-govbr/"
CATALOG = [
    {
        "titulo": "MGI — cadernos históricos (VB, RT, CD/FG/FCC)",
        "url": MGI
        + "tabela-de-remuneracao-dos-servidores-publicos-federais-civis-e-dos-ex-territorios-1",
        "nota": "Selecione edição, carreira, jornada e efeitos financeiros; a data da publicação não define a vigência.",
    },
    {
        "titulo": "Magistério — anexos de VB e RT anteriores a 2020",
        "url": "https://www.presidencia.gov.br/ccivil_03/_ato2015-2018/2016/lei/anexo/anl13325-i-iv.htm",
        "nota": "Há efeitos financeiros anteriores a 2020; conferir início e fim na fonte, sem cortar o histórico.",
    },
]


def get_batch(db, batch_id, *, lock=False):
    query = db.query(ImportacaoFonte).filter_by(id=batch_id)
    if lock:
        query = query.with_for_update().populate_existing()
    batch = query.first()
    if batch is None:
        raise HTTPException(status_code=404, detail="Prévia não encontrada.")
    return batch


@router.get("/catalogo")
def catalog(user: User = Depends(require_admin_or_dev)):
    return {
        "fontes": CATALOG,
        "formatos": ["csv", "xlsx", "ods", "pdf"],
        "conferencia": "Autenticidade, vigência e direito são conferidos manualmente pelo RH. Prefira a versão estruturada equivalente.",
    }


@router.get("")
def batches(
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    query = db.query(ImportacaoFonte)
    return {
        "total": query.count(),
        "itens": [
            {
                "id": item.id,
                "titulo": item.titulo,
                "obtido_em": item.obtido_em.isoformat(),
            }
            for item in query.order_by(ImportacaoFonte.id.desc())
            .offset((pagina - 1) * 20)
            .limit(20)
        ],
    }


@router.post("/previa")
@limiter.limit("10/minute")
async def preview(
    request: Request,
    metadados: str = Form(max_length=50000),
    arquivo: UploadFile = File(),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    try:
        config = ConfiguracaoFonte.model_validate_json(metadados)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail="Confira a origem, as datas e as regras de leitura."
        ) from exc
    content = bytearray()
    try:
        while chunk := await arquivo.read(1024 * 1024):
            content.extend(chunk)
            if len(content) > MAX_BYTES:
                raise HTTPException(status_code=413, detail="Arquivo excede 5 MB.")
    finally:
        await arquivo.close()
    filename = PurePosixPath((arquivo.filename or "fonte").replace("\\", "/")).name[
        :200
    ]
    if not preview_slots.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="Leitores de fonte ocupados. Aguarde e tente novamente.",
        )
    try:
        rows = await run_in_threadpool(read_source, bytes(content), filename, config)
    except SourceReadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        # Não ecoa detalhes XML, conteúdo do documento ou caminhos locais.
        raise HTTPException(
            status_code=422,
            detail="Não foi possível ler a fonte com segurança. Confira o arquivo ou use o cadastro manual validado.",
        ) from exc
    finally:
        preview_slots.release()
    batch = create_preview(
        db, config, filename, sha256(content).hexdigest(), rows, user.id
    )
    log_audit(
        db,
        "FONTE_PREVIA_CRIADA",
        f"Prévia: {batch.id}; linhas: {len(rows)}",
        user.id,
        request.client.host if request.client else None,
    )
    return source_json(db, batch)


@router.post("/manual")
def manual(
    request: Request,
    payload: CadastroManual,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    encoded = json.dumps(
        payload.model_dump(mode="json"), sort_keys=True, ensure_ascii=False
    )
    rows = [
        {
            "dados": data,
            "localizador": f"{payload.localizador}: registro {index + 1}",
            "erro": None,
        }
        for index, data in enumerate(payload.linhas)
    ]
    batch = create_preview(
        db,
        payload.origem,
        "cadastro.manual",
        sha256(encoded.encode()).hexdigest(),
        rows,
        user.id,
    )
    log_audit(
        db,
        "FONTE_MANUAL_PREVIA",
        f"Prévia: {batch.id}; linhas: {len(rows)}",
        user.id,
        request.client.host if request.client else None,
    )
    return source_json(db, batch)


@router.get("/{batch_id:int}")
def detail(
    batch_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    return source_json(db, get_batch(db, batch_id))


@router.put("/{batch_id:int}/linhas/{row_id}")
def edit(
    batch_id: int,
    row_id: int,
    payload: EditarLinha,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    batch = get_batch(db, batch_id, lock=True)
    row = (
        db.query(LinhaImportacaoFonte)
        .filter_by(id=row_id, lote_id=batch_id)
        .with_for_update()
        .populate_existing()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Linha não encontrada.")
    if row.versao != payload.versao or row.estado in TERMINAL:
        raise HTTPException(
            status_code=409,
            detail="Linha alterada ou já ativada. Atualize a prévia; referências confirmadas não são sobrescritas.",
        )
    _, errors = validate_line(payload.dados)
    row.dados_json = json.dumps(payload.dados, ensure_ascii=False)
    row.localizador = payload.localizador
    row.estado = "REJEITADA" if errors else "PENDENTE"
    row.problemas_json = json.dumps(errors, ensure_ascii=False)
    row.versao += 1
    log_audit(
        db,
        "FONTE_LINHA_REVISADA",
        f"Prévia: {batch.id}; linha: {row.id}",
        user.id,
        request.client.host if request.client else None,
    )
    return source_json(db, batch)


@router.post("/{batch_id:int}/ativar")
def activate_preview(
    batch_id: int,
    payload: AtivarFonte,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    batch = get_batch(db, batch_id, lock=True)
    activate(db, batch, payload, user.id)
    log_audit(
        db,
        "FONTE_ATIVACAO_CONFERIDA",
        f"Prévia: {batch.id}; linhas selecionadas: {len(payload.linhas)}",
        user.id,
        request.client.host if request.client else None,
    )
    return source_json(db, batch)


@router.get("/cobertura")
def coverage(
    inicio: date = date(2020, 1, 1),
    fim: date = Query(...),
    tipo: str = Query("SALARIO", pattern="^(SALARIO|FUNCAO|IQ)$"),
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    if fim < inicio:
        raise HTTPException(status_code=422, detail="Período de cobertura inválido.")
    model: Any = {"FUNCAO": EstruturaFuncao, "IQ": EstruturaIQ}.get(tipo, EstruturaRemuneratoria)
    query = db.query(model)
    items = []
    for structure in query.order_by(model.id).offset((pagina - 1) * 20).limit(20):
        groups: dict[str, list[tuple[date, date | None]]] = (
            {"VB": []} if tipo == "SALARIO" else {"IQ" if tipo == "IQ" else structure.componente: []}
        )
        titles: dict[str, str] = {}
        ref_model: Any = {"SALARIO": ReferenciaSalarial, "IQ": ReferenciaIQ}.get(tipo, ReferenciaFuncao)
        refs = db.query(ref_model).filter_by(estrutura_id=structure.id)
        if tipo == "SALARIO":
            refs = refs.filter_by(estado="CONFIRMADA")
        for ref in refs:
            span = (ref.inicio_vigencia, ref.fim_vigencia)
            groups["VB" if tipo == "SALARIO" else "IQ" if tipo == "IQ" else structure.componente].append(span)
            if tipo == "SALARIO":
                for rt in db.query(RetribuicaoReferencia).filter_by(
                    referencia_id=ref.id
                ):
                    groups.setdefault(
                        "RT: " + titles.setdefault(rt.titulacao_chave, rt.titulacao), []
                    ).append(span)
        fields = ("titulacao",) if tipo == "IQ" else (
            ("tipo_funcao", "codigo_funcao", "modalidade", "componente")
            if tipo == "FUNCAO"
            else (
                "carreira",
                "vinculo",
                "jornada",
                "versao_carreira",
                "classificacao_tae",
                "capacitacao_tae",
                "padrao_tae",
                "classe_docente",
                "nivel_docente",
            )
        )
        for component, intervals in groups.items():
            covered, gaps = coverage_intervals(intervals, inicio, fim)
            items.append(
                {
                    "estrutura_id": structure.id,
                    "posicao": {field: getattr(structure, field) for field in fields},
                    "componente": component,
                    "cobertos": covered,
                    "lacunas": gaps,
                }
            )
    return {
        "itens": items,
        "total_estruturas": query.count(),
        "pagina": pagina,
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "escopo": "Somente estruturas e titulações cadastradas. Ausência de estrutura/titulação também exige cadastro e conferência; não comprova cobertura completa.",
    }


@router.get("/funcoes")
def functions(
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    query = db.query(ReferenciaFuncao, EstruturaFuncao).join(EstruturaFuncao)
    return {
        "total": query.count(),
        "itens": [
            {
                "id": ref.id,
                "tipo_funcao": structure.tipo_funcao,
                "codigo_funcao": structure.codigo_funcao,
                "modalidade": structure.modalidade,
                "componente": structure.componente,
                "inicio_vigencia": ref.inicio_vigencia.isoformat(),
                "fim_vigencia": ref.fim_vigencia.isoformat()
                if ref.fim_vigencia
                else None,
                "valor": str(ref.valor),
                "fonte": ref.fonte,
            }
            for ref, structure in query.order_by(ReferenciaFuncao.id.desc())
            .offset((pagina - 1) * 20)
            .limit(20)
        ],
    }


@router.get("/origens")
def origins(
    referencia_id: int = Query(gt=0),
    tipo: str = Query("SALARIO", pattern="^(SALARIO|FUNCAO)$"),
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    column = (
        LinhaImportacaoFonte.referencia_id
        if tipo == "SALARIO"
        else LinhaImportacaoFonte.funcao_id
    )
    query = (
        db.query(LinhaImportacaoFonte, ImportacaoFonte)
        .join(ImportacaoFonte)
        .filter(column == referencia_id)
    )
    items = []
    for row, batch in (
        query.order_by(LinhaImportacaoFonte.id).offset((pagina - 1) * 20).limit(20)
    ):
        items.append(
            {
                "linha_id": row.id,
                "lote_id": batch.id,
                "titulo": batch.titulo,
                "url": batch.url,
                "obtido_em": batch.obtido_em.isoformat(),
                "publicado_em": batch.publicado_em.isoformat()
                if batch.publicado_em
                else None,
                "sha256": batch.sha256,
                "localizador": row.localizador,
                "dados": json.loads(row.dados_json),
                "estado": row.estado,
                "revisado_em": row.revisado_em.isoformat() if row.revisado_em else None,
                "revisado_por": row.revisado_por,
            }
        )
    return {
        "total": query.count(),
        "itens": items,
        "nota": "Histórico de origens e conferências por componente. Os valores atuais da referência podem ter sido revisados posteriormente.",
    }


@router.post("/cobertura/salarial")
def requested_coverage(
    payload: ConsultaCobertura,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin_or_dev),
):
    position = payload.posicao
    rows = (
        db.query(
            ReferenciaSalarial.inicio_vigencia,
            ReferenciaSalarial.fim_vigencia,
            RetribuicaoReferencia.titulacao_chave,
        )
        .join(
            EstruturaRemuneratoria,
            ReferenciaSalarial.estrutura_id == EstruturaRemuneratoria.id,
        )
        .outerjoin(
            RetribuicaoReferencia,
            RetribuicaoReferencia.referencia_id == ReferenciaSalarial.id,
        )
        .filter(
            EstruturaRemuneratoria.chave == position.chave_estrutura(),
            ReferenciaSalarial.estado == "CONFIRMADA",
        )
        .all()
    )
    groups = {"VB": {(row.inicio_vigencia, row.fim_vigencia) for row in rows}}
    if payload.titulacao and salary_key(payload.titulacao) != "n/a":
        title = salary_key(payload.titulacao)
        groups["RT: " + payload.titulacao] = {
            (row.inicio_vigencia, row.fim_vigencia)
            for row in rows
            if row.titulacao_chave == title
        }
    items = []
    for component, intervals in groups.items():
        covered, gaps = coverage_intervals(intervals, payload.inicio, payload.fim)
        items.append(
            {
                "estrutura_id": None,
                "posicao": position.model_dump(),
                "componente": component,
                "cobertos": covered,
                "lacunas": gaps,
            }
        )
    return {
        "itens": items,
        "total_estruturas": 1,
        "pagina": 1,
        "inicio": payload.inicio.isoformat(),
        "fim": payload.fim.isoformat(),
        "escopo": "Cobertura da posição e titulação solicitadas, inclusive quando ausentes do cadastro. Não comprova direito nem outras posições.",
    }
