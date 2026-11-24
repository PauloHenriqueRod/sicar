from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.tabelas_salariais import HistoricoCalculo
from app.models.user import User
from app.services.auth_service import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/stats")
def get_dashboard_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query_base = db.query(HistoricoCalculo)
    if current_user.role not in ["admin", "dev"]:
        query_base = query_base.filter(HistoricoCalculo.user_id == current_user.id)
    # Total de cálculos
    total_calculos = query_base.with_entities(func.count(HistoricoCalculo.id)).scalar() or 0
    
    # Total de usuários
    total_usuarios = db.query(func.count(User.id)).scalar() or 0
    
    # Cálculos por tipo (Substituição, Insalubridade, etc)
    tipos_raw = query_base.with_entities(HistoricoCalculo.tipo_calculo, func.count(HistoricoCalculo.id)).group_by(HistoricoCalculo.tipo_calculo).all()
    calculos_por_tipo = {t[0]: t[1] for t in tipos_raw}
    
    # Últimos 5 cálculos
    ultimos = query_base.order_by(HistoricoCalculo.data_calculo.desc()).limit(5).all()
    
    ultimos_json = []
    for h in ultimos:
        ultimos_json.append({
            "id": h.id,
            "data_calculo": h.data_calculo.isoformat(),
            "tipo_calculo": h.tipo_calculo,
            "matricula": h.matricula,
            "classe": h.classe,
            "nivel": h.nivel,
            "titulacao": h.titulacao
        })
        
    return {
        "total_calculos": total_calculos,
        "total_usuarios": total_usuarios,
        "calculos_por_tipo": calculos_por_tipo,
        "ultimos_calculos": ultimos_json
    }
