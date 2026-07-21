from astromesh.core.prompt_engine import PromptEngine


def test_render_simple_template():
    engine = PromptEngine()
    result = engine.render("Hello, {{ name }}!", {"name": "World"})
    assert result == "Hello, World!"


def test_render_with_missing_var():
    engine = PromptEngine()
    result = engine.render("Hello, {{ name }}!", {})
    assert result == "Hello, !"


def test_render_multiline():
    engine = PromptEngine()
    template = """You are {{ role }}.
Your task is {{ task }}.
{% for item in items %}
- {{ item }}
{% endfor %}"""
    result = engine.render(
        template,
        {
            "role": "an assistant",
            "task": "helping users",
            "items": ["search", "answer", "summarize"],
        },
    )
    assert "an assistant" in result
    assert "helping users" in result
    assert "- search" in result
    assert "- answer" in result
    assert "- summarize" in result


def test_register_and_render_template():
    engine = PromptEngine()
    engine.register_template("greeting", "Hi {{ user }}, welcome!")
    result = engine.render_template("greeting", {"user": "Alice"})
    assert result == "Hi Alice, welcome!"


def test_render_nonexistent_template():
    engine = PromptEngine()
    result = engine.render_template("does_not_exist", {"x": 1})
    assert result == ""


def test_templates_are_isolated_by_scope():
    engine = PromptEngine()
    engine.register_template("greeting", "Hola {{ user }} desde ventas", scope="ventas")
    engine.register_template("greeting", "Hola {{ user }} desde soporte", scope="soporte")

    assert engine.render_template("greeting", {"user": "Ana"}, scope="ventas") == (
        "Hola Ana desde ventas"
    )
    assert engine.render_template("greeting", {"user": "Ana"}, scope="soporte") == (
        "Hola Ana desde soporte"
    )


def test_scoped_template_is_not_visible_without_its_scope():
    engine = PromptEngine()
    engine.register_template("greeting", "Hola {{ user }}", scope="ventas")

    assert engine.render_template("greeting", {"user": "Ana"}) == ""


def test_unscoped_templates_keep_working():
    engine = PromptEngine()
    engine.register_template("greeting", "Hola {{ user }}")

    assert engine.render_template("greeting", {"user": "Ana"}) == "Hola Ana"
    assert engine.render_template("greeting", {"user": "Ana"}, scope="ventas") == ""
