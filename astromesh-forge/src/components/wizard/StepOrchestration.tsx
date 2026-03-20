import { useAgentEditorStore } from "../../stores/agent";
import { Card } from "../ui/Card";
import { Input } from "../ui/Input";

const PATTERNS = [
  {
    id: "react",
    name: "ReAct",
    description:
      "Reason-Act loop: the agent thinks, picks a tool, observes, repeats until done.",
  },
  {
    id: "plan_and_execute",
    name: "Plan & Execute",
    description:
      "Creates a full plan first, then executes each step sequentially.",
  },
  {
    id: "parallel_fan_out",
    name: "Parallel Fan-Out",
    description:
      "Splits work across parallel branches and merges the results.",
  },
  {
    id: "pipeline",
    name: "Pipeline",
    description:
      "Sequential chain where each step's output feeds the next step's input.",
  },
  {
    id: "supervisor",
    name: "Supervisor",
    description:
      "A supervisor agent delegates tasks to worker agents and coordinates results.",
  },
  {
    id: "swarm",
    name: "Swarm",
    description:
      "Agents hand off control to each other dynamically based on context.",
  },
];

export function StepOrchestration() {
  const config = useAgentEditorStore((s) => s.config);
  const updateSpec = useAgentEditorStore((s) => s.updateSpec);

  const orch = config.spec.orchestration;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-gray-100">
        Orchestration Pattern
      </h2>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {PATTERNS.map((p) => (
          <Card
            key={p.id}
            hoverable
            className={`cursor-pointer transition-all ${
              orch.pattern === p.id
                ? "border-cyan-500 ring-1 ring-cyan-500/50"
                : ""
            }`}
            onClick={() =>
              updateSpec("orchestration", { ...orch, pattern: p.id })
            }
          >
            <div className="flex items-start gap-3">
              <div
                className={`mt-1 w-4 h-4 rounded-full border-2 flex-shrink-0 ${
                  orch.pattern === p.id
                    ? "border-cyan-500 bg-cyan-500"
                    : "border-gray-600"
                }`}
              >
                {orch.pattern === p.id && (
                  <div className="w-full h-full rounded-full bg-cyan-500" />
                )}
              </div>
              <div>
                <p className="font-medium text-gray-100">{p.name}</p>
                <p className="text-xs text-gray-400 mt-1">{p.description}</p>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t border-gray-700">
        <Input
          label="Max Iterations"
          id="max-iterations"
          type="number"
          min={1}
          value={orch.max_iterations}
          onChange={(e) =>
            updateSpec("orchestration", {
              ...orch,
              max_iterations: parseInt(e.target.value, 10) || 1,
            })
          }
        />
        <Input
          label="Timeout (seconds)"
          id="timeout-seconds"
          type="number"
          min={1}
          value={orch.timeout_seconds ?? ""}
          onChange={(e) =>
            updateSpec("orchestration", {
              ...orch,
              timeout_seconds: e.target.value
                ? parseInt(e.target.value, 10)
                : undefined,
            })
          }
          placeholder="300"
        />
      </div>
    </div>
  );
}
