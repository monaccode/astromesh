from astromesh.orchestration.glyph_pattern import GlyphPattern
from bench.glyph.fixtures import SCENARIOS
from bench.glyph.harness import CountingModel, RunMetrics, run_scenario
from bench.glyph.run import render_report


def test_there_is_at_least_one_scenario_per_repo_agent():
    names = {s.name for s in SCENARIOS}
    assert any("autolink" in n for n in names)
    assert any("support" in n for n in names)


def test_every_scenario_declares_its_expected_answer_check():
    assert all(callable(s.expected) for s in SCENARIOS)


def test_every_scenario_tool_is_declared_in_its_schema_list():
    for scenario in SCENARIOS:
        declared = {t["function"]["name"] for t in scenario.tools}
        assert set(scenario.tool_impl) <= declared, scenario.name


def test_every_tool_declares_the_shape_it_returns():
    """Sin `returns` el modelo inventa nombres de campo y el pipe filtra a vacío."""
    for scenario in SCENARIOS:
        for tool in scenario.tools:
            assert tool["function"].get("returns"), f"{scenario.name}/{tool['function']['name']}"


def test_there_is_a_scenario_that_forces_long_chaining():
    """Contra un ReAct de 2 llamadas no hay round-trips que eliminar."""
    long_ones = [s for s in SCENARIOS if len(s.tools) >= 5]
    assert long_ones, "ningún escenario obliga a encadenar"


def test_the_rag_scenario_shares_everything_but_knowledge_with_its_twin():
    """Es el test que sostiene el experimento.

    Si los dos escenarios divergen en algo más que el knowledge, el delta del
    reporte deja de ser puro multiplicador y los números siguen pareciendo
    válidos. El fallo sería silencioso.
    """
    from bench.glyph.fixtures import SUPPORT, SUPPORT_RAG

    assert SUPPORT_RAG.query == SUPPORT.query
    assert SUPPORT_RAG.tools == SUPPORT.tools
    assert SUPPORT_RAG.tool_impl == SUPPORT.tool_impl
    assert SUPPORT_RAG.expected is SUPPORT.expected
    assert SUPPORT_RAG.reference_program == SUPPORT.reference_program
    assert SUPPORT_RAG.name != SUPPORT.name


def test_only_the_rag_scenario_declares_knowledge():
    """Los escenarios viejos no cambian: las corridas versionadas siguen comparables."""
    from bench.glyph.fixtures import SUPPORT_RAG

    with_knowledge = [s.name for s in SCENARIOS if s.knowledge]
    assert with_knowledge == [SUPPORT_RAG.name]


def test_the_knowledge_block_is_the_size_of_a_real_retrieval():
    """5 chunks, que es el top_k de config/rag/product-knowledge.rag.yaml."""
    from bench.glyph.fixtures import KNOWLEDGE_POLITICAS

    assert KNOWLEDGE_POLITICAS.count("\n\n") == 4  # 5 chunks separados por línea en blanco
    assert 3000 < len(KNOWLEDGE_POLITICAS) < 6000  # ~750-1500 tokens


def test_the_knowledge_uses_the_production_renderer():
    """Si el formato de producción cambia, el benchmark cambia con él."""
    from astromesh.rag.agent_rag import format_knowledge
    from bench.glyph.fixtures import KNOWLEDGE_POLITICAS, POLITICAS_CHUNKS

    assert format_knowledge(POLITICAS_CHUNKS) == KNOWLEDGE_POLITICAS


async def test_the_long_chain_reference_program_runs_and_answers_correctly():
    from bench.glyph.fixtures import LONG_CHAIN

    program = "```glyph\n" + LONG_CHAIN.reference_program + "\n```"
    model = CountingModel(_scripted([program, "Reservé B-777 en SC-A."]))
    metrics = await run_scenario(LONG_CHAIN, GlyphPattern(), model)
    assert metrics.correct is True
    assert metrics.tool_calls == 5


def _scripted(responses):
    it = iter(responses)

    async def provider_fn(messages, tools, role=None):
        class R:
            content = next(it)
            tool_calls = None
            usage = {"input_tokens": 500, "output_tokens": 60}

        return R()

    return provider_fn


async def test_counting_model_accumulates_usage_across_calls():
    async def provider_fn(messages, tools, role=None):
        class R:
            content = "hola"
            tool_calls = None
            usage = {"input_tokens": 100, "output_tokens": 20}

        return R()

    model = CountingModel(provider_fn)
    await model([{"role": "user", "content": "a"}], [])
    await model([{"role": "user", "content": "b"}], [])
    assert model.input_tokens == 200
    assert model.output_tokens == 40
    assert model.calls == 2


async def test_run_scenario_returns_metrics_for_a_scripted_glyph_run():
    scenario = SCENARIOS[0]
    program = "```glyph\n" + scenario.reference_program + "\n```"
    model = CountingModel(_scripted([program, "Listo, encontré OEM-1."]))

    metrics = await run_scenario(scenario, GlyphPattern(), model)
    assert isinstance(metrics, RunMetrics)
    assert metrics.pattern == "glyph"
    assert metrics.model_calls == 2
    assert metrics.tool_calls > 0
    assert metrics.wall_ms > 0
    assert metrics.correct is True


async def test_invalid_programs_are_counted():
    scenario = SCENARIOS[0]
    program = "```glyph\n" + scenario.reference_program + "\n```"
    model = CountingModel(_scripted(["```glyph\nx = = 1\n```", program, "ok"]))

    metrics = await run_scenario(scenario, GlyphPattern(), model)
    assert metrics.invalid_programs == 1


def _metrics(pattern, **overrides):
    base = {
        "scenario": "autolink-parts/cotizar-pastillas",
        "pattern": pattern,
        "input_tokens": 25000 if pattern == "react" else 8000,
        "output_tokens": 400 if pattern == "react" else 200,
        "model_calls": 6 if pattern == "react" else 2,
        "tool_calls": 3,
        "wall_ms": 900.0 if pattern == "react" else 350.0,
        "correct": True,
        "invalid_programs": 0,
    }
    return RunMetrics(**{**base, **overrides})


def test_the_report_shows_both_patterns_side_by_side():
    report = render_report([_metrics("react"), _metrics("glyph")])
    assert "| Métrica | ReAct | glyph |" in report
    assert "autolink-parts/cotizar-pastillas" in report


def test_the_report_holds_more_than_one_glyph_variant():
    """react vs glyph vs glyph-datos, en una sola tabla comparable."""
    report = render_report(
        [_metrics("react"), _metrics("glyph"), _metrics("glyph-datos", model_calls=1)]
    )
    assert "| Métrica | ReAct | glyph | glyph-datos |" in report
    assert "| Llamadas al modelo | 6 | 2 (-67%) | 1 (-83%) |" in report


def test_a_regression_names_the_variant_that_regressed():
    report = render_report(
        [_metrics("react"), _metrics("glyph"), _metrics("glyph-datos", correct=False)]
    )
    assert "**REGRESIÓN** en glyph-datos" in report


def test_the_report_computes_the_token_delta_as_a_percentage():
    report = render_report([_metrics("react"), _metrics("glyph")])
    # 25400 -> 8200 es una baja del 67,7%.
    assert "-68%" in report or "-67%" in report


def test_the_report_computes_the_latency_delta():
    report = render_report([_metrics("react"), _metrics("glyph")])
    assert "-61%" in report


def test_the_report_flags_a_correctness_regression():
    report = render_report([_metrics("react"), _metrics("glyph", correct=False)])
    assert "REGRESIÓN" in report


def test_the_report_surfaces_the_invalid_program_rate():
    report = render_report([_metrics("react"), _metrics("glyph", invalid_programs=2)])
    assert "Programas inválidos" in report


def test_the_report_states_that_there_is_no_automatic_threshold():
    report = render_report([_metrics("react"), _metrics("glyph")])
    assert "no hay umbral" in report.lower()


def test_a_scenario_measured_for_only_one_pattern_is_reported_as_incomplete():
    report = render_report([_metrics("glyph")])
    assert "incompleto" in report


# ---- tasa de validez ---------------------------------------------------------


def test_validity_rate_is_valid_over_samples():
    from bench.glyph.validity import ValidityResult

    assert ValidityResult(scenario="s", samples=4, valid=3).rate == 0.75


async def test_measure_counts_a_compiling_program_as_valid():
    from bench.glyph.fixtures import AUTOLINK
    from bench.glyph.validity import measure

    program = "```glyph\n" + AUTOLINK.reference_program + "\n```"
    model = CountingModel(_scripted([program] * 100))

    results = await measure(model, samples=2)
    autolink = next(r for r in results if r.scenario == AUTOLINK.name)
    assert autolink.valid == 2
    assert autolink.errors == []


async def test_measure_records_the_error_of_an_invalid_program():
    from bench.glyph.validity import measure

    model = CountingModel(_scripted(["```glyph\nx = = 1\n```"] * 100))
    results = await measure(model, samples=2)
    assert all(r.valid == 0 for r in results)
    assert all("GlyphSyntaxError" in e for r in results for e in r.errors)


def test_the_report_groups_repeated_errors():
    """Un mismo fallo N veces es una señal distinta de N fallos distintos."""
    from bench.glyph.validity import ValidityResult, render_report

    report = render_report(
        [ValidityResult(scenario="s", samples=3, valid=0, errors=["E: igual"] * 3)]
    )
    assert "**3x** E: igual" in report


def test_the_report_calls_a_high_rate_apt():
    from bench.glyph.validity import ValidityResult, render_report

    assert "Apto" in render_report([ValidityResult(scenario="s", samples=10, valid=9)])


def test_the_report_calls_a_low_rate_unfit_and_says_why():
    from bench.glyph.validity import ValidityResult, render_report

    report = render_report([ValidityResult(scenario="s", samples=10, valid=3)])
    assert "No apto" in report
    assert "mejor en código" in report


def test_the_report_flags_a_middling_rate_as_borderline():
    from bench.glyph.validity import ValidityResult, render_report

    assert "Al límite" in render_report([ValidityResult(scenario="s", samples=10, valid=6)])
