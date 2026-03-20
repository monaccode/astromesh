import { useAgentEditorStore } from "../../stores/agent";
import { Input } from "../ui/Input";

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function StepIdentity() {
  const config = useAgentEditorStore((s) => s.config);
  const setConfig = useAgentEditorStore((s) => s.setConfig);

  const { metadata, spec } = config;

  function updateField(updates: Partial<typeof config>) {
    setConfig({ ...config, ...updates });
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-100">Agent Identity</h2>

      <Input
        label="Display Name"
        id="display_name"
        value={spec.identity.display_name}
        onChange={(e) =>
          updateField({
            spec: {
              ...spec,
              identity: { ...spec.identity, display_name: e.target.value },
            },
          })
        }
        placeholder="My Assistant"
      />

      <Input
        label="Technical Name"
        id="name"
        value={metadata.name}
        onChange={(e) =>
          updateField({ metadata: { ...metadata, name: e.target.value } })
        }
        onBlur={(e) =>
          updateField({
            metadata: { ...metadata, name: slugify(e.target.value) },
          })
        }
        placeholder="my-assistant"
      />

      <div className="flex flex-col gap-1">
        <label htmlFor="description" className="text-sm text-gray-400">
          Description
        </label>
        <textarea
          id="description"
          className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 placeholder-gray-500 focus:outline-none focus:border-cyan-500 min-h-[100px] resize-y"
          value={spec.identity.description}
          onChange={(e) =>
            updateField({
              spec: {
                ...spec,
                identity: { ...spec.identity, description: e.target.value },
              },
            })
          }
          placeholder="Describe what this agent does..."
        />
      </div>

      <Input
        label="Tags (comma-separated)"
        id="tags"
        value={
          metadata.labels
            ? Object.keys(metadata.labels).join(", ")
            : ""
        }
        onChange={(e) => {
          const tags = e.target.value
            .split(",")
            .map((t) => t.trim())
            .filter(Boolean);
          const labels: Record<string, string> = {};
          tags.forEach((t) => {
            labels[t] = "true";
          });
          updateField({ metadata: { ...metadata, labels } });
        }}
        placeholder="chatbot, support, internal"
      />
    </div>
  );
}
