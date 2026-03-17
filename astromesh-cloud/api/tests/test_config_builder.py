from astromesh_cloud.services.config_builder import build_agent_config

def test_build_basic_config():
    wizard = {"name": "support", "display_name": "Support Bot", "system_prompt": "Help customers.", "model": "ollama/llama3", "tone": "professional"}
    config = build_agent_config(wizard, "acme")
    assert config["metadata"]["name"] == "acme--support"
    assert config["spec"]["model"]["primary"]["provider"] == "ollama"
    assert "professional" in config["spec"]["prompts"]["system"].lower()

def test_build_config_with_tools_and_guardrails():
    wizard = {"name": "research", "display_name": "Research Bot", "system_prompt": "Research.", "model": "openai/gpt-4o", "tools": ["web_search", "calculator"], "pii_filter": True, "content_filter": True, "memory_enabled": True, "orchestration": "plan_and_execute"}
    config = build_agent_config(wizard, "globex")
    assert len(config["spec"]["tools"]) == 2
    assert config["spec"]["guardrails"]["input"][0]["type"] == "pii_filter"
    assert config["spec"]["memory"]["conversational"]["backend"] == "sqlite"
    assert config["spec"]["orchestration"]["pattern"] == "plan_and_execute"

def test_runtime_name_namespaced():
    wizard = {"name": "bot", "display_name": "Bot", "system_prompt": "Hi.", "model": "ollama/mistral"}
    config = build_agent_config(wizard, "my-org")
    assert config["metadata"]["name"] == "my-org--bot"
