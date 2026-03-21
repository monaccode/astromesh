import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Wrench,
  Link2,
  Database,
  Shield,
  Cpu,
  Bot,
  Plus,
  ChevronUp,
  ChevronDown,
  Loader2,
} from "lucide-react";
import { useConnectionStore } from "../../../stores/connection";
import type { AgentMeta } from "../../../types/agent";
import {
  type PipelinePreset,
  presetsForSection,
  type PresetSection,
} from "../../../data/pipeline-presets";
import { Button } from "../../ui/Button";
import { Badge } from "../../ui/Badge";

export interface MicroToolboxProps {
  /** True if a preset with this conflict key prefix already exists on the canvas */
  isSlotTaken: (conflictKey: string) => boolean;
  onAddBuiltinTool: (tool: { name: string; description: string }) => void;
  onAddPreset: (preset: PipelinePreset) => void;
  onAddFallbackModel?: () => void;
  canAddFallbackModel: boolean;
}

interface ToolboxProps {
  onAddAgent: (agent: AgentMeta) => void;
  /** When set, show pipeline blocks for the micro (expanded) view */
  micro?: MicroToolboxProps;
}

const SECTION_LABEL: Record<PresetSection, { label: string; icon: typeof Wrench }> = {
  builtin: { label: "From your node", icon: Wrench },
  integrations: { label: "Connections", icon: Link2 },
  memory: { label: "Memory & data", icon: Database },
  safety: { label: "Safety", icon: Shield },
};

function SectionHeader({
  title,
  icon: Icon,
  open,
  onToggle,
}: {
  title: string;
  icon?: typeof Wrench;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      className="w-full flex items-center justify-between px-3 py-2 text-sm font-medium text-gray-300 hover:bg-gray-800 transition-colors"
      onClick={onToggle}
    >
      <span className="flex items-center gap-1.5">
        {Icon && <Icon size={14} className="text-gray-500" />}
        {title}
      </span>
      {open ? (
        <ChevronUp size={14} className="text-gray-500" />
      ) : (
        <ChevronDown size={14} className="text-gray-500" />
      )}
    </button>
  );
}

export function Toolbox({ onAddAgent, micro }: ToolboxProps) {
  const navigate = useNavigate();
  const client = useConnectionStore((s) => s.client);
  const connected = useConnectionStore((s) => s.connected);

  const [agents, setAgents] = useState<AgentMeta[]>([]);
  const [loadingAgents, setLoadingAgents] = useState(false);

  const [builtinTools, setBuiltinTools] = useState<{ name: string; description: string }[]>([]);
  const [loadingBuiltins, setLoadingBuiltins] = useState(false);

  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    builtin: true,
    integrations: true,
    memory: true,
    safety: true,
    agents: true,
    model: true,
  });

  const toggle = (key: string) =>
    setOpenSections((s) => ({ ...s, [key]: !s[key] }));

  useEffect(() => {
    if (!connected) return;
    setLoadingAgents(true);
    client
      .listAgents()
      .then(setAgents)
      .catch(() => setAgents([]))
      .finally(() => setLoadingAgents(false));
  }, [client, connected]);

  useEffect(() => {
    if (!micro || !connected) return;
    setLoadingBuiltins(true);
    client
      .listTools()
      .then(setBuiltinTools)
      .catch(() => setBuiltinTools([]))
      .finally(() => setLoadingBuiltins(false));
  }, [micro, connected, client]);

  const widthClass = micro ? "w-[290px]" : "w-[250px]";

  return (
    <div
      className={`${widthClass} bg-gray-900 border-r border-gray-800 h-full overflow-y-auto shrink-0`}
    >
      <div className="p-3 border-b border-gray-800">
        <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          {micro ? "Add blocks" : "Toolbox"}
        </h2>
        {micro && (
          <p className="text-xs text-gray-500 mt-1 leading-snug">
            Tap a tile to append to the pipeline. Select a box on the canvas to edit it.
          </p>
        )}
      </div>

      {micro && (
        <>
          <div className="border-b border-gray-800">
            <SectionHeader
              title={SECTION_LABEL.builtin.label}
              icon={SECTION_LABEL.builtin.icon}
              open={!!openSections.builtin}
              onToggle={() => toggle("builtin")}
            />
            {openSections.builtin && (
              <div className="px-2 pb-2 space-y-1">
                {loadingBuiltins && (
                  <div className="flex items-center gap-1.5 text-xs text-gray-500 px-2 py-1">
                    <Loader2 size={12} className="animate-spin" /> Loading tools…
                  </div>
                )}
                {!loadingBuiltins && !connected && (
                  <div className="text-xs text-gray-500 px-2 py-1">Connect to load tools.</div>
                )}
                {!loadingBuiltins &&
                  builtinTools.map((t) => (
                    <PresetTile
                      key={t.name}
                      title={t.name}
                      hint={t.description || "Built-in tool"}
                      disabled={false}
                      onClick={() => micro.onAddBuiltinTool(t)}
                    />
                  ))}
                {!loadingBuiltins && connected && builtinTools.length === 0 && (
                  <p className="text-xs text-gray-500 px-2">No built-in tools reported.</p>
                )}
              </div>
            )}
          </div>

          {(["integrations", "memory", "safety"] as const).map((section) => (
            <div key={section} className="border-b border-gray-800">
              <SectionHeader
                title={SECTION_LABEL[section].label}
                icon={SECTION_LABEL[section].icon}
                open={!!openSections[section]}
                onToggle={() => toggle(section)}
              />
              {openSections[section] && (
                <div className="px-2 pb-2 space-y-1">
                  {presetsForSection(section).map((p) => {
                    const blocked =
                      p.conflictKey !== undefined && micro.isSlotTaken(p.conflictKey);
                    return (
                      <PresetTile
                        key={p.id}
                        title={p.title}
                        hint={p.hint}
                        disabled={blocked}
                        onClick={() => !blocked && micro.onAddPreset(p)}
                      />
                    );
                  })}
                </div>
              )}
            </div>
          ))}

          {micro.onAddFallbackModel && (
            <div className="border-b border-gray-800">
              <SectionHeader
                title="Model"
                icon={Cpu}
                open={!!openSections.model}
                onToggle={() => toggle("model")}
              />
              {openSections.model && (
                <div className="px-2 pb-2">
                  <PresetTile
                    title="Fallback model"
                    hint="Secondary LLM if primary fails"
                    disabled={!micro.canAddFallbackModel}
                    onClick={() => micro.canAddFallbackModel && micro.onAddFallbackModel?.()}
                  />
                </div>
              )}
            </div>
          )}
        </>
      )}

      {!micro && (
        <div className="border-b border-gray-800">
          <SectionHeader
            title="Agents"
            icon={Bot}
            open={!!openSections.agents}
            onToggle={() => toggle("agents")}
          />

          {openSections.agents && (
            <div className="px-2 pb-2 space-y-1">
              {loadingAgents && (
                <div className="flex items-center gap-1.5 text-xs text-gray-500 px-2 py-1">
                  <Loader2 size={12} className="animate-spin" /> Loading…
                </div>
              )}
              {!loadingAgents && !connected && (
                <div className="text-xs text-gray-500 px-2 py-1">Not connected</div>
              )}
              {!loadingAgents &&
                agents.map((agent) => (
                  <button
                    key={agent.name}
                    type="button"
                    className="w-full text-left bg-gray-800 hover:bg-gray-750 border border-gray-700 hover:border-gray-600 rounded-lg p-2 transition-colors"
                    onClick={() => onAddAgent(agent)}
                  >
                    <div className="text-sm font-medium text-gray-200 truncate">
                      {agent.name}
                    </div>
                    <div className="text-xs text-gray-500 truncate">
                      {agent.description || "No description"}
                    </div>
                    <div className="mt-1">
                      <Badge
                        variant={
                          agent.status === "deployed"
                            ? "success"
                            : agent.status === "paused"
                              ? "warning"
                              : "default"
                        }
                      >
                        {agent.status}
                      </Badge>
                    </div>
                  </button>
                ))}

              <Button
                variant="secondary"
                icon={Plus}
                className="w-full mt-1 text-sm py-1.5"
                onClick={() => navigate("/wizard")}
              >
                Create New Agent
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PresetTile({
  title,
  hint,
  disabled,
  onClick,
}: {
  title: string;
  hint: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      className={`w-full text-left rounded-lg border p-2 transition-colors ${
        disabled
          ? "border-gray-800 bg-gray-900/50 text-gray-600 cursor-not-allowed"
          : "border-gray-700 bg-gray-800/80 hover:border-cyan-600/50 hover:bg-gray-800"
      }`}
      onClick={onClick}
    >
      <div className="text-sm font-medium text-gray-100">{title}</div>
      <div className="text-xs text-gray-500 mt-0.5 leading-snug">{hint}</div>
    </button>
  );
}

export type { PipelinePreset };
