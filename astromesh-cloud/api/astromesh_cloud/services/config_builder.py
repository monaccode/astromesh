"""Translates wizard JSON config into Astromesh agent YAML config."""

TONE_PREFIXES = {
    "professional": "Respond in a professional, clear tone.",
    "casual": "Respond in a friendly, conversational tone.",
    "technical": "Respond in a precise, technical tone with detail.",
    "empathetic": "Respond in a warm, empathetic tone showing understanding.",
}

ROUTING_MAP = {"cost_optimized": "cost_optimized", "latency_optimized": "latency_optimized", "quality_first": "quality_first"}
ORCHESTRATION_MAP = {"single_pass": "single_pass", "react": "react", "plan_and_execute": "plan_and_execute"}

def build_agent_config(wizard_config: dict, org_slug: str) -> dict:
    name = wizard_config["name"]
    runtime_name = f"{org_slug}--{name}"
    tone = wizard_config.get("tone", "professional")
    tone_prefix = TONE_PREFIXES.get(tone, TONE_PREFIXES["professional"])
    system_prompt = f"{tone_prefix}\n\n{wizard_config['system_prompt']}"
    model_str = wizard_config["model"]
    provider, model = model_str.split("/", 1) if "/" in model_str else ("ollama", model_str)

    config = {
        "apiVersion": "astromesh/v1",
        "kind": "Agent",
        "metadata": {"name": runtime_name, "version": "1.0"},
        "spec": {
            "identity": {"name": runtime_name, "role": wizard_config.get("display_name", name)},
            "model": {"primary": {"provider": provider, "model": model}, "routing": {"strategy": ROUTING_MAP.get(wizard_config.get("routing_strategy", "cost_optimized"), "cost_optimized")}},
            "prompts": {"system": system_prompt},
            "orchestration": {"pattern": ORCHESTRATION_MAP.get(wizard_config.get("orchestration", "react"), "react")},
        },
    }

    tools = wizard_config.get("tools", [])
    tool_configs = wizard_config.get("tool_configs", {})
    if tools:
        config["spec"]["tools"] = [{"name": t, "type": "builtin", **(tool_configs.get(t, {}))} for t in tools]
    if wizard_config.get("memory_enabled"):
        config["spec"]["memory"] = {"conversational": {"backend": "sqlite"}}
    guardrails = []
    if wizard_config.get("pii_filter"):
        guardrails.append({"type": "pii_filter", "action": "redact"})
    if wizard_config.get("content_filter"):
        guardrails.append({"type": "content_safety", "action": "block"})
    if guardrails:
        config["spec"]["guardrails"] = {"input": guardrails, "output": guardrails}
    return config
