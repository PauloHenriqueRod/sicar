import json
from decimal import Decimal, localcontext

from sqlalchemy import or_
from sqlalchemy.orm import Session, contains_eager, joinedload

from app.models.referencias_salariais import (
    EstruturaRemuneratoria,
    PendenciaSalarialLegada,
    ReferenciaSalarial,
    RetribuicaoReferencia,
)
from app.schemas.referencias_salariais import (
    ConsultaSalarial,
    PosicaoSalarial,
    ReferenciaEntrada,
)
from app.utils.clock import utcnow
from app.utils.salary_keys import salary_key


class ReferenciaSalarialPendente(ValueError):
    """Impede um salário presumido quando a consulta não é conclusiva."""


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def salvar_referencia(
    db: Session, dados: ReferenciaEntrada, user_id: int, *, item=None
):
    posicao = PosicaoSalarial.model_validate(
        dados.model_dump(include=set(PosicaoSalarial.model_fields))
    )
    estrutura = (
        db.query(EstruturaRemuneratoria)
        .filter_by(chave=posicao.chave_estrutura())
        .with_for_update()
        .first()
    )
    if estrutura is None:
        estrutura = EstruturaRemuneratoria(
            chave=posicao.chave_estrutura(), **posicao.model_dump()
        )
        db.add(estrutura)
        db.flush()
    conflict = db.query(ReferenciaSalarial).filter(
        ReferenciaSalarial.estrutura_id == estrutura.id,
        ReferenciaSalarial.estado == "CONFIRMADA",
        or_(
            ReferenciaSalarial.fim_vigencia.is_(None),
            ReferenciaSalarial.fim_vigencia >= dados.inicio_vigencia,
        ),
    )
    if dados.fim_vigencia is not None:
        conflict = conflict.filter(
            ReferenciaSalarial.inicio_vigencia <= dados.fim_vigencia
        )
    if item is not None:
        conflict = conflict.filter(ReferenciaSalarial.id != item.id)
    if dados.estado == "CONFIRMADA" and conflict.first():
        raise ValueError(
            "Há outra referência confirmada com vigência sobreposta para esta estrutura."
        )
    if item is None:
        item = ReferenciaSalarial()
        db.add(item)
    else:
        db.query(PendenciaSalarialLegada).filter_by(referencia_id=item.id).update(
            {"referencia_id": None}, synchronize_session="fetch"
        )
        item.retribuicoes.clear()
        db.flush()
    item.estrutura = estrutura
    item.inicio_vigencia, item.fim_vigencia = dados.inicio_vigencia, dados.fim_vigencia
    item.vencimento_basico, item.fonte, item.estado = (
        dados.vencimento_basico,
        dados.fonte,
        dados.estado,
    )
    item.conferido_por = user_id if dados.estado == "CONFIRMADA" else None
    item.conferido_em = utcnow() if dados.estado == "CONFIRMADA" else None
    item.retribuicoes = [
        RetribuicaoReferencia(
            titulacao=rt.titulacao,
            titulacao_chave=salary_key(rt.titulacao),
            valor=rt.valor,
        )
        for rt in dados.retribuicoes
    ]
    db.flush()  # O banco decide também conflitos concorrentes.
    db.refresh(item, attribute_names=["vencimento_basico"])
    if item.vencimento_basico != dados.vencimento_basico:
        raise ValueError(
            "O banco não preservou a precisão do VB. Utilize PostgreSQL e confira o valor original."
        )
    for rt, entrada in zip(item.retribuicoes, dados.retribuicoes, strict=True):
        db.refresh(rt, attribute_names=["valor"])
        if rt.valor != entrada.valor:
            raise ValueError(
                "O banco não preservou a precisão da RT. Utilize PostgreSQL e confira o valor original."
            )
    return item


def referencia_json(item: ReferenciaSalarial):
    return {
        "id": item.id,
        "estrutura_id": item.estrutura_id,
        **{
            name: getattr(item.estrutura, name) for name in PosicaoSalarial.model_fields
        },
        "inicio_vigencia": item.inicio_vigencia.isoformat(),
        "fim_vigencia": item.fim_vigencia.isoformat() if item.fim_vigencia else None,
        "vencimento_basico": decimal_text(item.vencimento_basico),
        "retribuicoes": [
            {"titulacao": rt.titulacao, "valor": decimal_text(rt.valor)}
            for rt in item.retribuicoes
        ],
        "fonte": item.fonte,
        "estado": item.estado,
        "conferido_em": item.conferido_em.isoformat() if item.conferido_em else None,
    }


def resolve_salary(
    db: Session, consulta: ConsultaSalarial | None, titulacao: str = "N/A"
):
    if consulta is None:
        raise ReferenciaSalarialPendente(
            "Informe a data salarial, carreira, vínculo, jornada, estrutura da carreira e posição para consultar uma referência confirmada."
        )
    if consulta.carreira != "TAE" and not titulacao.strip():
        raise ReferenciaSalarialPendente("Informe a titulação docente ou N/A explicitamente quando não houver RT; ela não é presumida.")
    # VB, RT e posição precisam pertencer à mesma leitura do banco. Selectin
    # permitiria combinar o VB antigo com a RT confirmada por outra transação.
    candidatas = (
        db.query(ReferenciaSalarial)
        .join(ReferenciaSalarial.estrutura)
        .options(
            contains_eager(ReferenciaSalarial.estrutura),
            joinedload(ReferenciaSalarial.retribuicoes),
        )
        .populate_existing()
        .filter(
            EstruturaRemuneratoria.chave == consulta.chave_estrutura(),
            ReferenciaSalarial.estado == "CONFIRMADA",
            ReferenciaSalarial.inicio_vigencia <= consulta.data_referencia,
            or_(
                ReferenciaSalarial.fim_vigencia.is_(None),
                ReferenciaSalarial.fim_vigencia >= consulta.data_referencia,
            ),
        )
        .all()
    )
    if len(candidatas) != 1:
        raise ReferenciaSalarialPendente(
            "Não há uma única referência confirmada cobrindo a data salarial. Confira lacunas ou conflitos de vigência."
        )
    referencia = candidatas[0]
    rt = None
    if titulacao.strip() and salary_key(titulacao) != salary_key("N/A"):
        rt = next(
            (
                r
                for r in referencia.retribuicoes
                if r.titulacao_chave == salary_key(titulacao)
            ),
            None,
        )
        if rt is None:
            raise ReferenciaSalarialPendente(
                "A referência confirmada não contém RT compatível com a titulação informada. Confira a titulação e a tabela; para TAE, IQ é informado no cálculo e a RT deve ser N/A."
            )
    with localcontext() as context:
        context.prec = 64
        value = referencia.vencimento_basico + (rt.valor if rt else Decimal(0))
    return value, {
        "origem": "referencia_salarial_confirmada",
        "referencia": referencia_json(referencia),
        "data_referencia": consulta.data_referencia.isoformat(),
        "valor_utilizado": float(value),
        "valor_decimal": str(value),
        "vencimento": {
            "id": referencia.id,
            "valor_decimal": str(referencia.vencimento_basico),
        },
        "retribuicao": {
            "id": rt.id,
            "titulacao": rt.titulacao,
            "valor_decimal": str(rt.valor),
        }
        if rt
        else None,
    }


def pendencia_json(item: PendenciaSalarialLegada):
    return {
        "id": item.id,
        "tabela_origem": item.tabela_origem,
        "id_origem": item.id_origem,
        "dados_originais": json.loads(item.dados_originais),
        "valor_original": item.valor_original,
        "valor_decimal": decimal_text(item.valor_decimal)
        if item.valor_decimal is not None
        else None,
        "referencia_id": item.referencia_id,
        "estado": "VINCULADA" if item.referencia_id else "PENDENTE",
        "motivo": item.motivo,
    }


def vincular_pendencia(db, pendencia, referencia):
    if referencia.estado != "CONFIRMADA" or pendencia.valor_decimal is None:
        raise ValueError(
            "Confira a conversão do valor e confirme a referência antes de vincular o legado."
        )
    original = json.loads(pendencia.dados_originais)
    if pendencia.tabela_origem == "tabela_vencimento_basico":
        matches = pendencia.valor_decimal == referencia.vencimento_basico
    else:
        matches = any(
            rt.titulacao_chave == salary_key(original.get("titulacao") or "")
            and rt.valor == pendencia.valor_decimal
            for rt in referencia.retribuicoes
        )
    if not matches:
        raise ValueError(
            "O valor/titulação legado não corresponde à referência selecionada."
        )
    # A correspondência da posição e vigência deve ter sido conferida pelo RH;
    # classe/ano legados não são utilizados para inferir essa equivalência.
    pendencia.referencia_id = referencia.id
    db.flush()
