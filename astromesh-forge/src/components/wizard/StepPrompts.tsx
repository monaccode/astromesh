import { useAgentEditorStore } from "../../stores/agent";

export function StepPrompts() {
  const config = useAgentEditorStore((s) => s.config);
  const updateSpec = useAgentEditorStore((s) => s.updateSpec);

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-gray-100">System Prompt</h2>
      <p className="text-sm text-gray-400">
        Write the system prompt for your agent. Jinja2 template syntax is
        supported.
      </p>
      <textarea
        className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-cyan-500 font-mono text-sm resize-y"
        style={{ minHeight: "300px" }}
        value={config.spec.prompts.system}
        onChange={(e) =>
          updateSpec("prompts", {
            ...config.spec.prompts,
            system: e.target.value,
          })
        }
        placeholder={`You are a helpful AI assistant.

You have access to the following tools:
{% for tool in tools %}
- {{ tool.name }}: {{ tool.description }}
{% endfor %}`}
      />
    </div>
  );
}
