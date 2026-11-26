"""Valida associações e aplicação explícita de observações no cálculo revisado."""

from decimal import Decimal, InvalidOperation

from app.services.pendencias import PendenciaApuracao
from app.utils.employee_identity import employee_key


def _pending(message):
    raise PendenciaApuracao("extracao_revisao_pendente", message)


def validar_revisao_extracao(data):
    review = data.revisao_extracao
    if review is None:
        return
    if not review.confirmado:
        _pending("Confira a associação dos documentos e os campos aplicados.")
    docs = {doc.id: doc for doc in review.documentos}
    expected = {
        (doc.id, block.id): block for doc in review.documentos for block in doc.blocos
    }
    associations = {(a.documento_id, a.bloco_id): a for a in review.associacoes}
    if set(associations) != set(expected):
        _pending(
            "Associe ou descarte explicitamente cada bloco identificado nos documentos."
        )
    substitute = getattr(data, "substituicao", None)
    plan = next(
        (
            getattr(data, name, None)
            for name in ("abono", "exercicios", "rescisao")
            if getattr(data, name, None)
        ),
        None,
    )
    plan_link = getattr(plan, "vinculo_id", None) or getattr(plan, "contrato_id", None)
    if plan_link and plan_link != review.vinculo_calculo:
        _pending("Vínculo da extração incompatível com o vínculo/contrato do cálculo.")
    for key, association in associations.items():
        block = expected[key]
        if not association.confirmado:
            _pending("Há documento sem associação conferida.")
        if association.pessoa == "DESCARTADO":
            if not association.justificativa:
                _pending("Justifique o descarte do bloco documental.")
            continue
        target_person = (
            substitute.titular_matricula
            if substitute and association.pessoa == "TITULAR"
            else data.matricula
        )
        target_link = (
            review.vinculo_titular
            if association.pessoa == "TITULAR"
            else review.vinculo_calculo
        )
        if association.pessoa == "TITULAR" and substitute is None:
            _pending("Papel titular permitido apenas no cálculo de substituição.")
        if block.papel_documental and (
            (block.papel_documental == "TITULAR") != (association.pessoa == "TITULAR")
        ):
            _pending("Papel associado diverge do titular/substituto explícito no ato.")
        if (
            not target_person
            or employee_key(association.matricula) != employee_key(target_person)
            or not target_link
            or association.vinculo != target_link
        ):
            _pending("Pessoa ou vínculo associado não corresponde ao cálculo.")
        if block.matricula and employee_key(block.matricula) != employee_key(
            association.matricula
        ):
            _pending(
                "Matrícula incompatível: descarte o bloco e utilize a fonte correta."
            )
        if block.vinculo and block.vinculo != association.vinculo:
            _pending(
                "Vínculo observado incompatível: documentos de vínculos diferentes não podem ser combinados."
            )
        if (not block.matricula or not block.vinculo) and not association.justificativa:
            _pending(
                "Justifique a identificação manual de pessoa/vínculo ausente no documento."
            )
    values = data.model_dump()
    destinations = set()
    for application in review.aplicacoes:
        doc = docs.get(application.documento_id)
        field = (
            next((f for f in doc.campos if f.id == application.campo_id), None)
            if doc
            else None
        )
        if field is None or field.pagina is None or field.estado == "AUSENTE":
            _pending("Campo aplicado sem valor observado identificável.")
        if field.campo == "periodo_ferias" and field.cancelada and not application.justificativa:
            _pending("Parcela cancelada exige revisão justificada do período aplicável.")
        association = associations.get((application.documento_id, field.bloco_id))
        if not association or association.pessoa == "DESCARTADO":
            _pending("Campo aplicado a partir de bloco descartado ou não associado.")
        path = tuple(application.destino)
        inicio_progressao = (
            path == ("progressao", "periodo", "inicio")
            and field.leitor_id == "portaria_docente_progressao"
            and field.campo == "efeitos_financeiros"
        )
        if field.campo == "modalidade_progressao" and path != ("progressao", "modalidade"):
            _pending("A modalidade observada exige o campo de modalidade da progressão.")
        semantic_targets = {
            "nome": {"nome"},
            "matricula": {"matricula", "titular_matricula"},
            "inicio_exercicio": {"inicio_exercicio", "data_exercicio"},
            "percentual_iq": {"percentual_iq", "incentivo"},
            "percentual_adicional_sugerido": {"percentual_adicional", "percentual", "percentual_insalubridade"},
            "jornada": {"jornada"},
            "data_documento": {"data_documento"},
            "data_publicacao": {"data_publicacao"},
            "efeitos_financeiros": {"efeitos_financeiros"},
            "inicio_designacao": {"inicio"},
            "fim_designacao": {"ultimo_dia_considerado"},
            "codigo_funcao_substituida": {"codigo_funcao"},
            "tipo_funcao_substituida": {"tipo_funcao"},
        }
        if (
            field.campo in semantic_targets
            and str(path[-1]) not in semantic_targets[field.campo]
            and not inicio_progressao
        ):
            _pending(
                "Destino incompatível com a data ou função explicitamente observada no ato."
            )
        designated_function = field.campo in (
            "codigo_funcao_substituida",
            "tipo_funcao_substituida",
        )
        if designated_function and path[:3] != (
            "substituicao",
            "estado_inicial",
            "substituida",
        ):
            _pending(
                "Código da função designada exige o destino da função substituída."
            )
        titular_target = (
            len(path) > 1
            and path[0] == "substituicao"
            and (
                path[1] in ("titular_matricula", "afastamentos_titular")
                or (len(path) > 2 and path[1:3] == ("estado_inicial", "substituida"))
            )
        )
        if (
            association.pessoa == "SERVIDOR"
            and titular_target
            and not designated_function
        ):
            _pending("Fonte do substituto não pode preencher dados do titular.")
        if association.pessoa == "TITULAR" and not titular_target:
            _pending("Fonte do titular não pode preencher os dados do substituto.")
        if (
            path in destinations
            or path[0] == "revisao_extracao"
            or any(
                str(key)
                in (
                    "regra",
                    "conferido",
                    "confirmada",
                    "confirmado",
                    "conferido_pelo_rh",
                    "documentos",
                )
                for key in path
            )
        ):
            _pending(
                "Destino repetido ou reservado: resolva o conflito antes de aplicar."
            )
        destinations.add(path)
        if any(isinstance(key, int) and key < 0 for key in path):
            _pending("Índice de destino inválido.")
        current = values
        try:
            for key in path:
                if isinstance(key, int) and application.registro_id:
                    if (
                        not isinstance(current, list)
                        or not isinstance(current[key], dict)
                        or current[key].get("id") != application.registro_id
                    ):
                        _pending(
                            "O registro aplicado foi removido ou mudou de posição; refaça a vinculação da fonte."
                        )
                if not isinstance(current, (dict, list)):
                    _pending("Destino não pode atravessar um campo escalar.")
                current = (
                    current[key] if isinstance(current, dict) else current[int(key)]
                )
        except (KeyError, IndexError, TypeError, ValueError):
            _pending("Destino do dado extraído não existe no formulário final.")
        if path[:2] == ("progressao", "bases_mensais_origem"):
            if len(path) != 5 or not isinstance(path[2], int) or path[3] not in ("vb", "rt") or path[4] != "valor":
                _pending("Associe a rubrica ao valor mensal de VB ou RT.")
            base = values["progressao"]["bases_mensais_origem"][path[2]]
            codigo = "00001" if path[3] == "vb" else "82606"
            if (field.campo != "rubrica" or field.rubrica != codigo or field.competencia != base["competencia"]
                or field.natureza != "R" or field.sequencia != "0"):
                _pending("A competência, a rubrica e a natureza da folha precisam corresponder à base mensal vinculada.")
        if current is None or isinstance(current, (dict, list, bool)):
            _pending("O destino precisa ser um campo preenchido do cálculo.")
        revised = application.valor_revisado
        if (
            application.valor_anterior is not None
            and not application.justificativa.strip()
        ):
            _pending("Justifique a substituição do valor ou da fonte anterior.")
        equal = str(current) == revised
        if isinstance(current, (Decimal, int, float)):
            try:
                equal = Decimal(str(current)) == Decimal(revised)
            except InvalidOperation:
                equal = False
        if not equal:
            _pending(
                "Valor final diverge da revisão registrada; confira novamente o campo aplicado."
            )
        same_observation = field.valor == revised
        if field.valor is not None and field.campo in (
            "rubrica",
            "quantidade_anuenios",
        ):
            try:
                same_observation = Decimal(field.valor) == Decimal(revised)
            except InvalidOperation:
                same_observation = False
        if (
            not same_observation or field.estado != "EXTRAIDO"
        ) and not application.justificativa:
            _pending(
                "Justifique a edição ou resolução de ambiguidade do campo extraído."
            )
