import html

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.tabelas_salariais import (
    TabelaRetribuicaoTitulacao,
    TabelaVencimentoBasico,
)
from app.models.user import User
from app.routers.auth_router import log_audit
from app.services.auth_service import get_current_user
from app.utils.salary_keys import salary_key

router = APIRouter(prefix="/tabelas", tags=["Gestao Tabelas"])


def ensure_available(db, model, classe, nivel, ano, titulacao=None, exclude_id=None):
    query = db.query(model).filter(model.classe_chave == salary_key(classe), model.nivel == nivel, model.ano == ano)
    if titulacao is not None:
        query = query.filter(model.titulacao_chave == salary_key(titulacao))
    if exclude_id is not None:
        query = query.filter(model.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=409, detail="Já existe um registro para essa combinação e vigência.")


def audit_table(db, action, target, user_id, ip):
    # A restrição única resolve também corridas entre processos.
    try:
        db.flush()
        from app.db.salary_reference_migration import sync_legacy_salary_rows
        sync_legacy_salary_rows(db.connection())
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Conflito ao gravar a vigência salarial.")
    log_audit(db, action, target, user_id, ip)

def require_admin_or_dev(user: User = Depends(get_current_user)):
    if user.role not in ["admin", "dev"]:
        raise HTTPException(status_code=403, detail="Permissão negada. Apenas Admin ou Dev.")
    return user

class VencimentoResponse(BaseModel):
    id: int
    classe: str
    nivel: int
    ano: int
    valor: float

class TitulacaoResponse(BaseModel):
    id: int
    classe: str
    nivel: int
    titulacao: str
    ano: int
    valor: float

@router.get("/vencimentos", response_model=list[VencimentoResponse])
def listar_vencimentos(ano: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_dev)):
    query = db.query(TabelaVencimentoBasico)
    if ano:
        query = query.filter(TabelaVencimentoBasico.ano <= ano)
    
    todos = query.order_by(TabelaVencimentoBasico.ano.desc()).all()
    
    if not ano:
        return todos
        
    vigentes = {}
    for item in todos:
        chave = (item.classe, item.nivel)
        if chave not in vigentes:
            vigentes[chave] = item
    return list(vigentes.values())

@router.get("/titulacoes", response_model=list[TitulacaoResponse])
def listar_titulacoes(ano: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_dev)):
    query = db.query(TabelaRetribuicaoTitulacao)
    if ano:
        query = query.filter(TabelaRetribuicaoTitulacao.ano <= ano)
        
    todos = query.order_by(TabelaRetribuicaoTitulacao.ano.desc()).all()
    
    if not ano:
        return todos
        
    vigentes = {}
    for item in todos:
        chave = (item.classe, item.nivel, item.titulacao)
        if chave not in vigentes:
            vigentes[chave] = item
    return list(vigentes.values())

class UpdateValorRequest(BaseModel):
    valor: float = Field(ge=0, allow_inf_nan=False)
    ano_vigente: int | None = Field(default=None, ge=1, le=9999, strict=True)

@router.put("/vencimentos/{item_id}")
def atualizar_vencimento(item_id: int, request_body: UpdateValorRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_dev)):
    item = db.query(TabelaVencimentoBasico).filter(TabelaVencimentoBasico.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Não encontrado")
        
    valor_anterior = item.valor
    ano_destino = request_body.ano_vigente or item.ano
    ensure_available(db, TabelaVencimentoBasico, item.classe, item.nivel, ano_destino, exclude_id=item.id)
    if request_body.ano_vigente and item.ano < request_body.ano_vigente:
        novo = TabelaVencimentoBasico(
            classe=item.classe,
            nivel=item.nivel,
            ano=request_body.ano_vigente,
            valor=request_body.valor
        )
        db.add(novo)
    else:
        item.valor = request_body.valor
        if request_body.ano_vigente and item.ano > request_body.ano_vigente:
             item.ano = request_body.ano_vigente
             
    audit_table(db, "TABELA_VENCIMENTO_ATUALIZADA", f"Origem: {item.id}; vigência: {ano_destino}; R${valor_anterior} -> R${request_body.valor}", current_user.id, request.client.host if request.client else None)
    return {"message": "Atualizado com sucesso"}

@router.put("/titulacoes/{item_id}")
def atualizar_titulacao(item_id: int, request_body: UpdateValorRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_dev)):
    item = db.query(TabelaRetribuicaoTitulacao).filter(TabelaRetribuicaoTitulacao.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Não encontrado")
        
    valor_anterior = item.valor
    ano_destino = request_body.ano_vigente or item.ano
    ensure_available(db, TabelaRetribuicaoTitulacao, item.classe, item.nivel, ano_destino, item.titulacao, item.id)
    if request_body.ano_vigente and item.ano < request_body.ano_vigente:
        novo = TabelaRetribuicaoTitulacao(
            classe=item.classe,
            nivel=item.nivel,
            titulacao=item.titulacao,
            ano=request_body.ano_vigente,
            valor=request_body.valor
        )
        db.add(novo)
    else:
        item.valor = request_body.valor
        if request_body.ano_vigente and item.ano > request_body.ano_vigente:
            item.ano = request_body.ano_vigente
             
    audit_table(db, "TABELA_TITULACAO_ATUALIZADA", f"Origem: {item.id}; vigência: {ano_destino}; R${valor_anterior} -> R${request_body.valor}", current_user.id, request.client.host if request.client else None)
    return {"message": "Atualizado com sucesso"}

class CreateVencimentoRequest(BaseModel):
    classe: str = Field(min_length=1, max_length=100)
    nivel: int = Field(gt=0, strict=True)
    ano: int = Field(ge=1, le=9999, strict=True)
    valor: float = Field(ge=0, allow_inf_nan=False)

@router.post("/vencimentos")
def criar_vencimento(request_body: CreateVencimentoRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_dev)):
    # Sanitização de Input (prevenção de Stored XSS)
    classe_sanitizada = html.escape(request_body.classe.strip())
    
    if not salary_key(classe_sanitizada) or "%" in classe_sanitizada:
        raise HTTPException(status_code=400, detail="Informe uma classe válida.")
    ensure_available(db, TabelaVencimentoBasico, classe_sanitizada, request_body.nivel, request_body.ano)
        
    novo = TabelaVencimentoBasico(
        classe=classe_sanitizada,
        nivel=request_body.nivel,
        ano=request_body.ano,
        valor=request_body.valor
    )
    db.add(novo)
    audit_table(db, "TABELA_VENCIMENTO_CRIADA", f"{classe_sanitizada}/N{request_body.nivel}/{request_body.ano}: R${request_body.valor}", current_user.id, request.client.host if request.client else None)
    return {"message": "Criado com sucesso"}

class CreateTitulacaoRequest(BaseModel):
    classe: str = Field(min_length=1, max_length=100)
    nivel: int = Field(gt=0, strict=True)
    titulacao: str = Field(min_length=1, max_length=100)
    ano: int = Field(ge=1, le=9999, strict=True)
    valor: float = Field(ge=0, allow_inf_nan=False)

@router.post("/titulacoes")
def criar_titulacao(request_body: CreateTitulacaoRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_admin_or_dev)):
    # Sanitização de Input (prevenção de Stored XSS)
    classe_sanitizada = html.escape(request_body.classe.strip())
    titulacao_sanitizada = html.escape(request_body.titulacao.strip())
    
    if not salary_key(classe_sanitizada) or not salary_key(titulacao_sanitizada) or "%" in classe_sanitizada or "%" in titulacao_sanitizada:
        raise HTTPException(status_code=400, detail="Informe classe e titulação válidas.")
    ensure_available(db, TabelaRetribuicaoTitulacao, classe_sanitizada, request_body.nivel, request_body.ano, titulacao_sanitizada)
        
    novo = TabelaRetribuicaoTitulacao(
        classe=classe_sanitizada,
        nivel=request_body.nivel,
        titulacao=titulacao_sanitizada,
        ano=request_body.ano,
        valor=request_body.valor
    )
    db.add(novo)
    audit_table(db, "TABELA_TITULACAO_CRIADA", f"{classe_sanitizada}/N{request_body.nivel}/{titulacao_sanitizada}/{request_body.ano}: R${request_body.valor}", current_user.id, request.client.host if request.client else None)
    return {"message": "Criado com sucesso"}
