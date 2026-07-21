"""El desglose por modelo tiene que sobrevivir al modelo Pydantic de la respuesta."""

from astromesh.api.routes.agents import UsageInfo


def test_usage_info_carries_the_by_model_breakdown():
    usage = UsageInfo(
        tokens_in=180,
        tokens_out=35,
        model="gpt-4o",
        by_model=[
            {
                "provider": "openai",
                "model": "gpt-4o",
                "role": "reasoning",
                "calls": 2,
                "tokens_in": 150,
                "tokens_out": 30,
                "cost": 0.75,
            },
            {
                "provider": "ollama",
                "model": "centinela-4b",
                "role": "classification",
                "calls": 1,
                "tokens_in": 30,
                "tokens_out": 5,
                "cost": 0.0,
            },
        ],
    )

    dumped = usage.model_dump()
    assert len(dumped["by_model"]) == 2
    assert dumped["by_model"][0]["model"] == "gpt-4o"
    assert dumped["by_model"][0]["calls"] == 2
    assert dumped["by_model"][1]["provider"] == "ollama"


def test_usage_info_without_breakdown_still_valid():
    """Compatibilidad hacia atrás: los campos planos solos siguen siendo válidos."""
    usage = UsageInfo(tokens_in=10, tokens_out=4, model="gpt-4o-mini")
    assert usage.by_model == []
