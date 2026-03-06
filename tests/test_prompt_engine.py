from astromech.core.prompt_engine import PromptEngine


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
    result = engine.render(template, {
        "role": "an assistant",
        "task": "helping users",
        "items": ["search", "answer", "summarize"],
    })
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
