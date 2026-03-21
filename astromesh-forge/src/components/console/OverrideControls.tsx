import { SlidersHorizontal } from "lucide-react";
import { useConsoleStore } from "../../stores/console";
import { Toggle } from "../ui/Toggle";

export function OverrideControls() {
  const { agentConfig, overrides, setOverride } = useConsoleStore();

  const tools = agentConfig?.spec.tools ?? [];

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-1 text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold">
        <SlidersHorizontal size={12} />
        Parameter Overrides
      </div>

      <div>
        <div className="text-xs text-gray-400 mb-1">Model</div>
        <input
          type="text"
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-cyan-500"
          placeholder={agentConfig?.spec.model?.primary?.model ?? "model"}
          value={overrides.model ?? ""}
          onChange={(e) =>
            setOverride("model", e.target.value || undefined)
          }
        />
      </div>

      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-gray-400">Temperature</span>
          <span className="text-cyan-400">
            {overrides.temperature ?? agentConfig?.spec.model?.primary?.parameters?.temperature ?? 0.7}
          </span>
        </div>
        <input
          type="range"
          min="0"
          max="2"
          step="0.1"
          className="w-full accent-cyan-500"
          value={
            overrides.temperature ??
            agentConfig?.spec.model?.primary?.parameters?.temperature ??
            0.7
          }
          onChange={(e) => setOverride("temperature", Number(e.target.value))}
        />
      </div>

      <div>
        <div className="text-xs text-gray-400 mb-1">Max Tokens</div>
        <input
          type="number"
          className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-100 focus:outline-none focus:border-cyan-500"
          placeholder="2048"
          value={overrides.max_tokens ?? ""}
          onChange={(e) =>
            setOverride(
              "max_tokens",
              e.target.value ? Number(e.target.value) : undefined,
            )
          }
        />
      </div>

      {tools.length > 0 && (
        <div>
          <div className="text-[9px] uppercase tracking-[1.5px] text-gray-500 font-semibold mb-2">
            Tools
          </div>
          <div className="flex flex-col gap-1.5">
            {tools.map((tool) => (
              <div
                key={tool.name}
                className="bg-gray-800 rounded px-2 py-1.5"
              >
                <Toggle
                  label={tool.name}
                  checked={!overrides.disabledTools.includes(tool.name)}
                  onChange={(checked) => {
                    if (checked) {
                      setOverride(
                        "disabledTools",
                        overrides.disabledTools.filter((t) => t !== tool.name),
                      );
                    } else {
                      setOverride("disabledTools", [
                        ...overrides.disabledTools,
                        tool.name,
                      ]);
                    }
                  }}
                />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
