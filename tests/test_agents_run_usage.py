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


async def test_run_response_carries_tokens_cached_per_model(client, monkeypatch):
    """Contrato de /run: tokens_cached sobrevive al modelo Pydantic de la respuesta."""
    from astromesh.api.routes import agents as agents_module

    class FakeRuntime:
        async def run(self, *_args, **_kwargs):
            return {
                "answer": "listo",
                "steps": [],
                "trace": {
                    "spans": [
                        {
                            "attributes": {
                                "model": "kimi-k2.6",
                                "provider": "kimi",
                                "input_tokens": 5000,
                                "output_tokens": 100,
                                "cached_tokens": 4096,
                            }
                        }
                    ]
                },
            }

    monkeypatch.setattr(agents_module, "_runtime", FakeRuntime())
    resp = await client.post("/v1/agents/any-agent/run", json={"query": "hola"})

    assert resp.status_code == 200
    assert resp.json()["usage"]["by_model"][0]["tokens_cached"] == 4096


def test_model_usage_defaults_tokens_cached_to_zero():
    from astromesh.api.routes.agents import ModelUsage

    assert ModelUsage().tokens_cached == 0
