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
