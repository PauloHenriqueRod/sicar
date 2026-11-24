from app.services.apuracao_periodos import apurar_periodos
from app.services.progressao_eventos import aplicar_reflexos


def calcular_adicionais(plan, db):
    apoio: dict = {}
    for event in plan.reflexos:
        apoio.setdefault(event.data_base, set()).update(event.formulas_base)
    result = apurar_periodos(plan, db, formulas_apoio=apoio)
    result = aplicar_reflexos(plan, result)
    result["tipo_adicionais"] = "concessoes_v1"
    result["nota_adicional"] = (
        "A apuração depende da confirmação de espécie, percentual, base, regra e vigência pelo RH. A razão entre rubricas não concede direito. Recebimentos representam o adicional e seus reflexos já pagos."
    )
    return result
