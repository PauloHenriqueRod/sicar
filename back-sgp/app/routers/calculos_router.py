import json
import logging
import os
import tempfile
from datetime import date
from decimal import Decimal, DecimalException
from typing import Any, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.models.cobertura_adicionais import RevisaoCalculo
from app.models.tabelas_salariais import HistoricoCalculo
from app.models.user import User
from app.schemas.calculos import (
    MODELOS_CALCULO,
    AbonoParcelasDados,
    AdicionaisDados,
    ApuracaoPeriodosDados,
    ExerciciosParcelasDados,
    ProgressaoEventosDados,
    RescisaoPeriodosDados,
    SubstituicaoPeriodosDados,
    entradas_calculo,
)
from app.schemas.progressao_eventos import PlanoProgressao
from app.services.apuracao_periodos import PendenciaApuracao
from app.services.auth_service import get_current_user
from app.services.calculation_service import execute_calculation
from app.services.cobertura_adicionais import registrar_cobertura
from app.services.history_service import history_page
from app.services.pdf_export import UnsupportedPDFCharacterError, generate_pdf_report
from app.services.pdf_extraction import extract_pdf_data
from app.services.salary_references import ReferenciaSalarialPendente
from app.utils.clock import utcnow
from app.utils.conversor import ConversorSaneador
from app.utils.limiter import limiter

router = APIRouter(dependencies=[Depends(get_current_user)])


@router.get("/calculos/contratos/extracao")
def contrato_extracao():
    from app.schemas.extracao_documentos import (
        ArquivoExtracao,
        DocumentoExtraido,
        RevisaoExtracao,
    )
    return {"versao_contrato": 2, "documento": DocumentoExtraido.model_json_schema(), "revisao": RevisaoExtracao.model_json_schema(), "metadado_arquivo": ArquivoExtracao.model_json_schema()}
logger = logging.getLogger(__name__)


class CalcularRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tipo_calculo: str = Field(max_length=40)
    dados_extraidos: dict[str, Any] = Field(max_length=100)
    idempotency_key: UUID | None = None


class ExportarPDFRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    historico_id: int = Field(gt=0, strict=True)


@router.get("/calculos/contratos/apuracao-periodos")
def contrato_apuracao_periodos():
    """JSON Schema autenticado, gerado a partir do contrato executado pelo motor."""
    return ApuracaoPeriodosDados.model_json_schema()


@router.get("/calculos/contratos/progressao")
def contrato_progressao():
    return ProgressaoEventosDados.model_json_schema()


@router.post("/calculos/progressao/previa-folha")
@limiter.limit("30/minute")
def previa_folha_docente(request: Request, payload: PlanoProgressao, db: Session = Depends(get_db)):
    from app.services.progressao_eventos import calcular_progressao_eventos
    from app.services.progressao_relatorio import comparativo_folha

    if not payload.bases_mensais_origem or any(item.rt is None for item in payload.bases_mensais_origem):
        raise HTTPException(422, detail="Confira o VB e a RT de todas as competências.")
    try:
        return {"parcelas": comparativo_folha(calcular_progressao_eventos(payload, db))}
    except PendenciaApuracao as exc:
        raise HTTPException(422, detail=str(exc)) from exc


@router.get("/calculos/contratos/adicionais")
def contrato_adicionais():
    return AdicionaisDados.model_json_schema()


@router.get("/calculos/contratos/exercicios-anteriores")
def contrato_exercicios():
    return ExerciciosParcelasDados.model_json_schema()


@router.get("/calculos/contratos/abono")
def contrato_abono():
    return AbonoParcelasDados.model_json_schema()


@router.get("/calculos/contratos/rescisao")
def contrato_rescisao():
    return RescisaoPeriodosDados.model_json_schema()


@router.post("/calculos/rescisao/previa")
def previa_rescisao_endpoint(payload: RescisaoPeriodosDados):
    from app.services.rescisao_periodos import previa_rescisao
    try:
        return previa_rescisao(payload.rescisao)
    except PendenciaApuracao as exc:
        raise HTTPException(status_code=400, detail=[{"loc": ["dados_extraidos", "rescisao"], "msg": str(exc), "type": exc.codigo}]) from exc


@router.get("/calculos/contratos/substituicao")
def contrato_substituicao():
    return SubstituicaoPeriodosDados.model_json_schema()


@router.get("/calculos/referencias-funcao")
def referencias_funcao(
    inicio: date,
    fim: date,
    pagina: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    from sqlalchemy import or_

    from app.models.fontes_oficiais import EstruturaFuncao, ReferenciaFuncao

    if fim < inicio:
        raise HTTPException(400, "O fim da consulta não pode anteceder o início.")
    rows = (
        db.query(ReferenciaFuncao, EstruturaFuncao)
        .join(EstruturaFuncao)
        .filter(
            ReferenciaFuncao.inicio_vigencia <= fim,
            or_(
                ReferenciaFuncao.fim_vigencia.is_(None),
                ReferenciaFuncao.fim_vigencia >= inicio,
            ),
        )
    )
    return {
        "total": rows.count(),
        "pagina": pagina,
        "itens": [
            {
                "id": ref.id,
                "tipo_funcao": fn.tipo_funcao,
                "codigo_funcao": fn.codigo_funcao,
                "modalidade": fn.modalidade,
                "componente": fn.componente,
                "inicio_vigencia": ref.inicio_vigencia.isoformat(),
                "fim_vigencia": ref.fim_vigencia.isoformat()
                if ref.fim_vigencia
                else None,
                "valor": str(ref.valor),
                "fonte": ref.fonte,
            }
            for ref, fn in rows.order_by(ReferenciaFuncao.id)
            .offset((pagina - 1) * 100)
            .limit(100)
        ],
    }


def _snapshot(registro: HistoricoCalculo) -> dict[str, Any]:
    from app.utils.crypto import decrypt_data

    raw = registro.resultado_json
    # A migração protege snapshots legados; texto claro não permite contornar Fernet.
    return json.loads(decrypt_data(raw))


def _resultado_historico(registro: HistoricoCalculo) -> str:
    data = _snapshot(registro)
    return json.dumps(data["resultado_calculo"] if data.get("versao") == 2 else data)


async def _extrair_arquivo_v2(arquivo: UploadFile, tipo_calculo: str):
    import hashlib

    from app.schemas.extracao_documentos import DocumentoExtraido
    name = ConversorSaneador.sanitizar_texto(arquivo.filename or "arquivo.pdf")[:200]
    path = None
    try:
        if not arquivo.filename or not arquivo.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "Formato não suportado; envie PDF ou preencha manualmente.")
        if await arquivo.read(5) != b"%PDF-":
            raise HTTPException(400, "Arquivo sem assinatura PDF válida.")
        await arquivo.seek(0)
        size = 0
        digest = hashlib.sha256()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            path = tmp.name
            while chunk := await arquivo.read(1024 * 1024):
                size += len(chunk)
                if size > 5 * 1024 * 1024:
                    raise HTTPException(413, "O arquivo excede o limite de 5 MB.")
                tmp.write(chunk)
                digest.update(chunk)
        data = await run_in_threadpool(extract_pdf_data, path, f"v2:{tipo_calculo}")
        doc = DocumentoExtraido.model_validate(data["_extracao_v2"])
        doc.nome_arquivo = name
        doc.impressao = digest.hexdigest()
        return {"filename": name, "dados_extraidos": {}, "extracao": doc.model_dump(mode="json")}
    finally:
        if path and os.path.exists(path):
            os.unlink(path)
        await arquivo.close()


async def _extrair_pdf(request: Request, tipo_calculo: str, arquivos: list[UploadFile], versao_extracao: int = 1):
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
    CHUNK_SIZE = 1024 * 1024  # 1 MB
    MAX_FILES = 10
    resultados = []
    if versao_extracao not in (1, 2):
        raise HTTPException(400, "Versão de extração não suportada.")
    if tipo_calculo == "apuracao_periodos" and versao_extracao == 1:
        raise HTTPException(400, "A apuração por períodos utiliza o contrato de extração versão 2.")
    if tipo_calculo not in {
        "substituicao",
        "insalubridade",
        "abono",
        "rescisao",
        "progressao",
        "exercicio_anterior",
        "apuracao_periodos",
    }:
        raise HTTPException(status_code=400, detail="Tipo de cálculo desconhecido")

    if not arquivos or len(arquivos) > MAX_FILES:
        raise HTTPException(
            status_code=413, detail=f"Envie entre 1 e {MAX_FILES} arquivos por lote."
        )

    falhas = []
    for file_index, arquivo in enumerate(arquivos):
        if versao_extracao == 2:
            # Falhas de arquivo são isoladas; autenticação e limites globais já
            # foram validados antes desta etapa. O temporário é limpo pelo legado.
            try:
                item = await _extrair_arquivo_v2(arquivo, tipo_calculo)
                item["indice_arquivo"] = file_index
                resultados.append(item)
            except HTTPException as exc:
                falhas.append({"indice_arquivo": file_index, "filename": ConversorSaneador.sanitizar_texto(arquivo.filename or "arquivo.pdf")[:200], "codigo": f"pdf_{exc.status_code}", "mensagem": exc.detail})
            except Exception:
                falhas.append({"indice_arquivo": file_index, "filename": ConversorSaneador.sanitizar_texto(arquivo.filename or "arquivo.pdf")[:200], "codigo": "pdf_falha", "mensagem": "Não foi possível interpretar este arquivo; preencha manualmente ou tente novamente."})
            continue
        if not arquivo.filename or not arquivo.filename.endswith(".pdf"):
            raise HTTPException(
                status_code=400, detail=f"O arquivo {arquivo.filename} deve ser um PDF"
            )

        magic_bytes = await arquivo.read(5)
        if magic_bytes != b"%PDF-":
            raise HTTPException(
                status_code=400,
                detail=f"O arquivo {arquivo.filename} não é um PDF autêntico",
            )
        await arquivo.seek(0)

        file_size = 0
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            try:
                while chunk := await arquivo.read(CHUNK_SIZE):
                    file_size += len(chunk)
                    if file_size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Arquivo {arquivo.filename} muito grande. O limite é de 5MB.",
                        )
                    tmp.write(chunk)
            except Exception:
                tmp.close()
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

        try:
            dados_extraidos = await run_in_threadpool(
                extract_pdf_data, tmp_path, tipo_calculo
            )
        except HTTPException:
            raise
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise HTTPException(
                status_code=500,
                detail="Erro ao processar PDF. Não foi possível ler um dos arquivos enviados.",
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        candidates = dados_extraidos.pop("_candidatos_substituicao", None)
        payment_observations = dados_extraidos.pop("_pagamentos_substituicao", None)
        fontes_rescisao = dados_extraidos.pop("_fontes_rescisao", None)
        observacoes_abono = dados_extraidos.pop("_observacoes_abono", None)
        candidatos_exercicios = dados_extraidos.pop("_candidatos_exercicios", None)
        resultados.append(
            {
                "filename": ConversorSaneador.sanitizar_texto(arquivo.filename),
                "dados_extraidos": dados_extraidos,
                **({"candidatos_exercicios": candidatos_exercicios} if candidatos_exercicios is not None else {}),
                **({"observacoes_abono": observacoes_abono} if observacoes_abono is not None else {}),
                **({"fontes_rescisao": fontes_rescisao} if fontes_rescisao is not None else {}),
                **({"candidatos_substituicao": candidates} if candidates is not None else {}),
                **({"pagamentos_observados": payment_observations} if payment_observations is not None else {}),
            }
        )

    if versao_extracao == 2:
        return {"versao_contrato": 2, "resultados": resultados, "falhas": falhas,
                "resumo": {"recebidos": len(arquivos), "interpretados": len(resultados), "falhas": len(falhas)}}
    return {"resultados": resultados}


@router.post("/extrair-pdf")
@limiter.limit("20/minute")
async def extrair_pdf(
    request: Request,
    tipo_calculo: str = Form(...),
    arquivos: list[UploadFile] = File(...),
    versao_extracao: int = Form(1),
    metadados_arquivos: str | None = Form(None, max_length=10000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.routers.auth_router import log_audit

    ip = request.client.host if request.client else None
    try:
        metadata = []
        if metadados_arquivos is not None:
            from pydantic import TypeAdapter

            from app.schemas.extracao_documentos import ArquivoExtracao

            try:
                metadata = TypeAdapter(list[ArquivoExtracao]).validate_json(metadados_arquivos)
            except ValueError as exc:
                raise HTTPException(422, "Metadados dos arquivos inválidos.") from exc
            if len(metadata) != len(arquivos) or len({m.id for m in metadata}) != len(metadata):
                raise HTTPException(422, "Associe um identificador único a cada arquivo enviado.")
        result = await _extrair_pdf(request, tipo_calculo, arquivos, versao_extracao)
        # Os resultados/falhas podem ter nomes repetidos. O processamento da rota
        # é sequencial; a correlação é feita por índice de entrada, nunca por nome.
        if metadata and versao_extracao == 2:
            for item in result.get("resultados", []) + result.get("falhas", []):
                index = item.get("indice_arquivo")
                if index is None:
                    continue
                meta = metadata[index]
                item["arquivo_id"] = meta.id
                if "extracao" in item:
                    doc = item["extracao"]
                    doc["arquivo_id"], doc["categoria_informada"] = meta.id, meta.categoria
                    expected = {"financeira": {"FICHA_SIAPE"}, "cadastro": {"CADASTRO_FUNCIONAL"},
                                "ferias": {"CACOFERIAS"}, "ato": {"PORTARIA_UFPI_DOCENTE", "PORTARIA_UFPI_TAE", "ATO_UFPI_SUBSTITUICAO"}, "ata": set()}
                    if tipo_calculo == "progressao" and any(
                        leitor["identificador"] == "portaria_docente_progressao"
                        for leitor in doc.get("leitores", [])
                    ):
                        expected["ata"] = {"PORTARIA_UFPI_DOCENTE"}
                    if (meta.categoria in expected and doc["layout"] not in {"NAO_SUPORTADO", "MISTO"}
                            and doc["layout"] not in expected[meta.categoria]):
                        doc["avisos"] = (doc["avisos"] + ["O conteúdo reconhecido difere da seção selecionada; confira o tipo do documento."])[:100]
    except Exception as exc:
        status = exc.status_code if isinstance(exc, HTTPException) else 500
        log_audit(
            db,
            "PDF_EXTRACAO_FALHOU",
            f"Documentos: {len(arquivos)}; status: {status}",
            current_user.id,
            ip,
        )
        raise
    log_audit(db, "PDF_EXTRAIDO", f"Documentos: {len(arquivos)}; falhas: {len(result.get('falhas', []))}", current_user.id, ip)
    return result


def _dados_utilizados(dados: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    """Identificação efetiva, sem alterar as entradas usadas na idempotência."""
    utilizados = dict(dados)
    for salario, classe, nivel in (
        ("salario_contrato", "classe", "nivel"),
        ("salario_antigo", "classe_antiga", "nivel_antigo"),
        ("salario_novo", "classe_atual", "nivel_atual"),
    ):
        origem = trace.get("referencias_salariais", {}).get(salario, {})
        if origem.get("origem") != "referencia_salarial_confirmada":
            continue
        posicao = origem["referencia"]
        tae = posicao["carreira"] == "TAE"
        utilizados[classe] = posicao["classificacao_tae" if tae else "classe_docente"]
        utilizados[nivel] = posicao["padrao_tae" if tae else "nivel_docente"]
    return utilizados


def _existing_request(db: Session, user_id: int, key: str | None):
    if key is None:
        return None
    return (
        db.query(HistoricoCalculo)
        .filter(
            HistoricoCalculo.user_id == user_id,
            HistoricoCalculo.idempotency_key == key,
        )
        .first()
    )


def _normalizar_revisao_vazia(value: Any) -> Any:
    if isinstance(value, dict) and isinstance(value.get("revisao_extracao"), dict):
        review = value["revisao_extracao"]
        if review.get("historico_aplicacoes") == []:
            review = {key: item for key, item in review.items() if key != "historico_aplicacoes"}
            return {**value, "revisao_extracao": review}
    return value


def _mesmas_entradas_decimais(salvo: Any, atual: Any) -> bool:
    """Compara números sem confundir escala decimal com mudança de valor.

    Somente campos Decimal do contrato são convertidos. Nomes, matrículas e
    outros textos continuam sujeitos à comparação textual exata.
    """
    if isinstance(atual, Decimal):
        if isinstance(salvo, bool) or not isinstance(salvo, (str, int, float, Decimal)):
            return False
        try:
            return Decimal(str(salvo)) == atual
        except DecimalException:
            return False
    if isinstance(atual, date):
        return salvo == atual.isoformat()
    if isinstance(atual, dict):
        salvo, atual = _normalizar_revisao_vazia(salvo), _normalizar_revisao_vazia(atual)
        return (
            isinstance(salvo, dict)
            and salvo.keys() == atual.keys()
            and all(
                _mesmas_entradas_decimais(salvo[chave], valor)
                for chave, valor in atual.items()
            )
        )
    if isinstance(atual, list):
        return (
            isinstance(salvo, list)
            and len(salvo) == len(atual)
            and all(
                _mesmas_entradas_decimais(a, b)
                for a, b in zip(salvo, atual, strict=True)
            )
        )
    return salvo == atual


def _replay(
    registro: HistoricoCalculo,
    tipo: str,
    dados: dict[str, Any],
    entradas_decimais: dict[str, Any],
):
    saved = _snapshot(registro)
    # A apuração publica Decimal como texto; a escala desse texto não altera
    # o valor. O contrato tipado distingue esses números dos identificadores.
    dados_iguais = (
        _mesmas_entradas_decimais(saved.get("dados_extraidos"), entradas_decimais)
        if tipo == "apuracao_periodos"
        or "progressao" in entradas_decimais
        or "adicionais" in entradas_decimais
        or "substituicao" in entradas_decimais
        or "rescisao" in entradas_decimais
        or "abono" in entradas_decimais
        or "exercicios" in entradas_decimais
        else _normalizar_revisao_vazia(saved.get("dados_extraidos")) == _normalizar_revisao_vazia(dados)
    )
    if registro.tipo_calculo != tipo or not dados_iguais:
        raise HTTPException(
            status_code=409,
            detail="Esta tentativa já foi usada com outros dados. Inicie um novo cálculo.",
        )
    precise_saved = saved.get("rastreabilidade", {}).get("entradas_decimais")
    if precise_saved is not None and not _mesmas_entradas_decimais(
        precise_saved, entradas_decimais
    ):
        raise HTTPException(
            status_code=409,
            detail="Esta tentativa já foi usada com outros dados. Inicie um novo cálculo.",
        )
    return {
        "resultado_calculo": saved["resultado_calculo"],
        "historico_id": registro.id,
    }


@router.post("/calcular")
@limiter.limit("30/minute")
async def calcular_valores(
    request: Request,
    payload: CalcularRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    model = MODELOS_CALCULO.get(payload.tipo_calculo)
    if model is None:
        raise HTTPException(status_code=400, detail="Tipo de cálculo desconhecido")
    try:
        # O corpo já passou pelo contrato externo. Ler as frações do JSON como
        # Decimal evita perder precisão antes da validação dos campos financeiros.
        dados_decimais = json.loads(await request.body(), parse_float=Decimal)[
            "dados_extraidos"
        ]
        if payload.tipo_calculo == "progressao" and "progressao" in dados_decimais:
            model = ProgressaoEventosDados
        if payload.tipo_calculo == "insalubridade" and "adicionais" in dados_decimais:
            model = AdicionaisDados
        if payload.tipo_calculo == "substituicao" and "substituicao" in dados_decimais:
            model = SubstituicaoPeriodosDados
        if payload.tipo_calculo == "rescisao" and "rescisao" in dados_decimais:
            model = RescisaoPeriodosDados
        if payload.tipo_calculo == "abono" and "abono" in dados_decimais:
            model = AbonoParcelasDados
        if payload.tipo_calculo == "exercicio_anterior" and "exercicios" in dados_decimais:
            model = ExerciciosParcelasDados
        revisados = model.model_validate(dados_decimais)
    except ValidationError as exc:
        # Nunca ecoa o conteúdo original, documentos ou detalhes de exceções.
        raise HTTPException(
            status_code=400,
            detail=[
                {
                    "loc": ["dados_extraidos", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in exc.errors()[:100]
            ],
        ) from exc
    # Mantém números no contrato público/legado; a representação decimal exata
    # fica no snapshot de rastreabilidade e é conferida nas novas tentativas.
    decimal_encoder = (
        str
        if isinstance(
            revisados,
            (
                ApuracaoPeriodosDados,
                ProgressaoEventosDados,
                AdicionaisDados,
                SubstituicaoPeriodosDados,
                RescisaoPeriodosDados,
                AbonoParcelasDados,
                ExerciciosParcelasDados,
            ),
        )
        else float
    )
    dados = jsonable_encoder(
        entradas_calculo(revisados), custom_encoder={Decimal: decimal_encoder}
    )
    entradas_decimais = entradas_calculo(revisados)
    key = str(payload.idempotency_key) if payload.idempotency_key else None
    existing = _existing_request(db, current_user.id, key)
    if existing is not None:
        return _replay(existing, payload.tipo_calculo, dados, entradas_decimais)
    try:
        resultado, trace = execute_calculation(revisados, db)
        utilizados = _dados_utilizados(dados, trace)
        snapshot_json = json.dumps(
            {
                "versao": 2,
                "dados_extraidos": dados,
                "dados_utilizados": utilizados,
                "resultado_calculo": resultado,
                "rastreabilidade": trace,
            },
            allow_nan=False,
        )
    except PendenciaApuracao as exc:
        raise HTTPException(
            status_code=400,
            detail=[
                {
                    "loc": [
                        "dados_extraidos",
                        "revisao_extracao" if exc.codigo.startswith("extracao_") else "exercicios"
                        if isinstance(revisados, ExerciciosParcelasDados)
                        else "abono"
                        if isinstance(revisados, AbonoParcelasDados)
                        else "rescisao"
                        if payload.tipo_calculo == "rescisao"
                        else "substituicao"
                        if isinstance(revisados, SubstituicaoPeriodosDados)
                        else "adicionais"
                        if isinstance(revisados, AdicionaisDados)
                        else "progressao"
                        if isinstance(revisados, ProgressaoEventosDados)
                        else "apuracao",
                    ],
                    "msg": str(exc),
                    "type": exc.codigo,
                }
            ],
        ) from exc
    except ReferenciaSalarialPendente as exc:
        raise HTTPException(
            status_code=400,
            detail=[
                {
                    "loc": ["dados_extraidos"],
                    "msg": str(exc),
                    "type": "referencia_salarial_pendente",
                }
            ],
        ) from exc
    except (ValueError, OverflowError, DecimalException):
        raise HTTPException(
            status_code=400,
            detail="Confira os dados e as tabelas salariais da competência. Não foi possível concluir o cálculo.",
        )
    try:
        from app.utils.crypto import encrypt_data

        classe = str(utilizados.get("classe_atual", utilizados.get("classe", "")))
        nivel = utilizados.get("nivel_atual", utilizados.get("nivel"))
        titulacao = str(dados.get("titulacao", "N/A"))
        if isinstance(revisados, SubstituicaoPeriodosDados):
            fn = revisados.substituicao.estado_inicial.substituida
            classe, nivel, titulacao = (
                f"{fn.tipo_funcao} {fn.codigo_funcao}",
                None,
                "N/A",
            )
        if isinstance(
            revisados, (ApuracaoPeriodosDados, ProgressaoEventosDados, AdicionaisDados)
        ):
            # Índices do histórico representam o estado inicial declarado;
            # a linha do tempo completa permanece no snapshot do cálculo.
            estado = (
                revisados.adicionais.estado_inicial
                if isinstance(revisados, AdicionaisDados)
                else revisados.apuracao.estado_inicial
                if isinstance(revisados, ApuracaoPeriodosDados)
                else revisados.progressao.estado_inicial
            )
            posicao = estado.posicao
            classe = (
                "Técnico Administrativo"
                if posicao.carreira == "TAE"
                else str(posicao.classe_docente)
            )
            nivel = (
                posicao.padrao_tae
                if posicao.carreira == "TAE"
                else posicao.nivel_docente
            )
            titulacao = estado.titulacao
        historico = HistoricoCalculo(
            data_calculo=utcnow(),
            tipo_calculo=payload.tipo_calculo,
            matricula=str(dados.get("matricula", "N/A")),
            classe=classe,
            nivel=nivel,
            titulacao=titulacao,
            resultado_json=encrypt_data(snapshot_json),
            user_id=current_user.id,
            idempotency_key=key,
        )
        db.add(historico)
        db.flush()
        registrar_cobertura(db, revisados, resultado, historico, current_user)
        from app.routers.auth_router import log_audit

        # Histórico e auditoria são confirmados na mesma transação.
        log_audit(
            db,
            "CALCULO_SALVO",
            f"Histórico: {historico.id}",
            current_user.id,
            request.client.host if request.client else None,
        )
    except PendenciaApuracao as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=[{"loc": ["dados_extraidos"], "msg": str(exc), "type": exc.codigo}],
        ) from exc
    except IntegrityError:
        db.rollback()
        existing = _existing_request(db, current_user.id, key)
        if existing is not None:
            return _replay(existing, payload.tipo_calculo, dados, entradas_decimais)
        raise HTTPException(
            status_code=500,
            detail="Não foi possível salvar o cálculo no histórico. Tente novamente.",
        )
    except Exception as exc:
        db.rollback()
        logger.error(
            "Não foi possível persistir o histórico do cálculo: %s", type(exc).__name__
        )
        raise HTTPException(
            status_code=500,
            detail="Não foi possível salvar o cálculo no histórico. Tente novamente.",
        )
    return {"resultado_calculo": resultado, "historico_id": historico.id}


def _historico_json(registro: HistoricoCalculo, substituido_por=None):
    return {
        "id": registro.id,
        "data_calculo": registro.data_calculo.isoformat()
        if registro.data_calculo
        else "",
        "tipo_calculo": registro.tipo_calculo,
        "matricula": registro.matricula,
        "classe": registro.classe,
        "nivel": registro.nivel,
        "titulacao": registro.titulacao,
        "resultado_json": _resultado_historico(registro),
        "substituido_por": substituido_por,
    }


def _historico_acessivel(db, user, identifier):
    query = db.query(HistoricoCalculo).filter(HistoricoCalculo.id == identifier)
    if user.role not in ("admin", "dev"):
        query = query.filter(HistoricoCalculo.user_id == user.id)
    record = query.first()
    if record is None:
        raise HTTPException(404, "Cálculo não encontrado.")
    return record


@router.get("/historico/{historico_id}")
def consultar_memoria(
    historico_id: int,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = _historico_acessivel(db, current_user, historico_id)
    snapshot = _snapshot(record)
    revision = db.get(RevisaoCalculo, record.id)
    previous = (
        db.query(RevisaoCalculo).filter(RevisaoCalculo.novo_id == record.id).first()
    )
    response.headers["Cache-Control"] = "no-store"
    return {
        "id": record.id,
        "tipo_calculo": record.tipo_calculo,
        "snapshot": snapshot,
        "entradas_recalculo": snapshot.get("rastreabilidade", {}).get(
            "entradas_decimais", snapshot.get("dados_extraidos")
        )
        if snapshot.get("versao") == 2
        else None,
        "anterior_id": previous.anterior_id if previous else None,
        "substituido_por": revision.novo_id if revision else None,
        "pode_recalcular": snapshot.get("versao") == 2
        and isinstance(snapshot.get("dados_extraidos"), dict),
    }


@router.get("/historico")
async def listar_historico(
    pagina: int | None = Query(default=None, ge=1),
    tamanho_pagina: int = Query(default=10, ge=1, le=100),
    busca: str = Query(default="", max_length=100),
    tipo_calculo: str = Query(default="", max_length=40),
    classe: str = Query(default="", max_length=300),
    titulacao: str = Query(default="", max_length=300),
    ordenar_por: Literal[
        "data_calculo", "matricula", "tipo_calculo", "classe"
    ] = "data_calculo",
    ordem: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        query = db.query(HistoricoCalculo)
        if current_user.role not in ("admin", "dev"):
            query = query.filter(HistoricoCalculo.user_id == current_user.id)
        # Compatibilidade com consumidores anteriores; a interface usa pagina explicitamente.
        if pagina is None:
            registros = (
                query.order_by(
                    HistoricoCalculo.data_calculo.desc(), HistoricoCalculo.id.desc()
                )
                .limit(50)
                .all()
            )
            revisoes = {
                anterior: novo
                for anterior, novo in db.query(
                    RevisaoCalculo.anterior_id, RevisaoCalculo.novo_id
                )
                .filter(RevisaoCalculo.anterior_id.in_([r.id for r in registros]))
                .all()
            }
            return [_historico_json(r, revisoes.get(r.id)) for r in registros]
        registros, total = history_page(
            query,
            pagina,
            tamanho_pagina,
            busca,
            tipo_calculo,
            classe,
            titulacao,
            ordenar_por,
            ordem,
        )
        revisoes = {
            anterior: novo
            for anterior, novo in db.query(
                RevisaoCalculo.anterior_id, RevisaoCalculo.novo_id
            )
            .filter(RevisaoCalculo.anterior_id.in_([r.id for r in registros]))
            .all()
        }
        return {
            "itens": [_historico_json(r, revisoes.get(r.id)) for r in registros],
            "total": total,
            "pagina": pagina,
            "tamanho_pagina": tamanho_pagina,
        }
    except Exception:
        raise HTTPException(
            status_code=500, detail="Não foi possível consultar o histórico."
        )


@router.post("/exportar-pdf")
@limiter.limit("20/minute")
async def exportar_pdf(
    request: Request,
    payload: ExportarPDFRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pdf_path = None
    query = db.query(HistoricoCalculo).filter(
        HistoricoCalculo.id == payload.historico_id
    )
    if current_user.role not in ("admin", "dev"):
        query = query.filter(HistoricoCalculo.user_id == current_user.id)
    historico = query.first()
    if not historico:
        raise HTTPException(status_code=404, detail="Cálculo não encontrado.")
    revision = db.get(RevisaoCalculo, historico.id)
    try:
        snapshot = _snapshot(historico)
        if snapshot.get("versao") != 2 or not isinstance(
            snapshot.get("dados_extraidos"), dict
        ):
            raise HTTPException(
                status_code=409,
                detail="Refaça o cálculo para exportar um relatório vinculado ao histórico.",
            )
        pdf_path = await run_in_threadpool(
            generate_pdf_report,
            tipo_calculo=historico.tipo_calculo,
            dados_extraidos=snapshot.get(
                "dados_utilizados", snapshot["dados_extraidos"]
            )
            | {
                "identificacao_historico": {
                    "historico_id": historico.id,
                    "versao_motor": snapshot.get("rastreabilidade", {}).get(
                        "versao_motor", "Não registrada"
                    ),
                    "situacao": f"VERSÃO HISTÓRICA SUBSTITUÍDA PELO #{revision.novo_id}"
                    if revision
                    else "Versão consultada",
                    "versao_snapshot": snapshot["versao"],
                }
            },
            resultado_calculo=snapshot["resultado_calculo"],
        )
        # Auditoria de exportação
        from app.routers.auth_router import log_audit

        log_audit(
            db,
            "PDF_EXPORTADO",
            f"Histórico: {historico.id}",
            current_user.id,
            request.client.host if request.client else None,
        )
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename="Relatorio_Oficial_Calculo.pdf",
            background=BackgroundTask(os.unlink, pdf_path),
        )
    except UnsupportedPDFCharacterError as exc:
        if pdf_path and os.path.exists(pdf_path):
            os.unlink(pdf_path)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except HTTPException:
        if pdf_path and os.path.exists(pdf_path):
            os.unlink(pdf_path)
        raise
    except Exception:
        if pdf_path and os.path.exists(pdf_path):
            os.unlink(pdf_path)
        raise HTTPException(
            status_code=500, detail="Não foi possível gerar o relatório PDF."
        )
