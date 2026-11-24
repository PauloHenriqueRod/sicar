"""Projeção de apresentação: mantém os dados e evita aprofundar a árvore do PDF."""


def report_state(state):
    rows = []
    for role, fn in (
        ("SUBSTITUIDA", state.get("substituida")),
        ("PROPRIA", state.get("propria", {}).get("funcao")),
    ):
        if not fn:
            continue
        for component in fn.get("componentes", []):
            rows.append(
                {
                    "papel": role,
                    **{key: value for key, value in fn.items() if key != "componentes"},
                    **{
                        key: value
                        for key, value in component.items()
                        if key != "valor_manual"
                    },
                    **(component.get("valor_manual") or {}),
                }
            )
    return {
        "situacao_propria": state.get("propria", {}).get("situacao"),
        "componentes_funcoes": rows,
        "opcao": state.get("opcao"),
    }


def substitution_report(data, result):
    plan = data["substituicao"]
    inputs = {key: value for key, value in data.items() if key != "substituicao"}
    inputs.update(
        {
            key: value
            for key, value in plan.items()
            if key not in ("estado_inicial", "eventos")
        }
    )
    inputs["estado_inicial"] = report_state(plan["estado_inicial"])
    inputs["eventos"] = [
        {
            **{key: value for key, value in event.items() if key != "estado"},
            **report_state(event["estado"]),
        }
        for event in plan.get("eventos", [])
    ]
    output = {
        **result,
        "segmentos": [
            {**segment, "estado": report_state(segment["estado"])}
            for segment in result["segmentos"]
        ],
    }
    return inputs, output
