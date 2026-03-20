import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAgentEditorStore } from "../../stores/agent";
import { useConnectionStore } from "../../stores/connection";
import { Button } from "../ui/Button";
import { StepIdentity } from "./StepIdentity";
import { StepModel } from "./StepModel";
import { StepTools } from "./StepTools";
import { StepOrchestration } from "./StepOrchestration";
import { StepSettings } from "./StepSettings";
import { StepPrompts } from "./StepPrompts";
import { StepReview } from "./StepReview";

const STEPS = [
  { label: "Identity", component: StepIdentity },
  { label: "Model", component: StepModel },
  { label: "Tools", component: StepTools },
  { label: "Orchestration", component: StepOrchestration },
  { label: "Settings", component: StepSettings },
  { label: "Prompts", component: StepPrompts },
  { label: "Review", component: StepReview },
];

export function WizardShell() {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const [currentStep, setCurrentStep] = useState(1);
  const [loadError, setLoadError] = useState<string | null>(null);

  const setConfig = useAgentEditorStore((s) => s.setConfig);
  const client = useConnectionStore((s) => s.client);

  useEffect(() => {
    if (!name) return;
    let cancelled = false;
    (async () => {
      try {
        const config = await client.getAgent(name);
        if (!cancelled) setConfig(config);
      } catch (err) {
        if (!cancelled)
          setLoadError(
            err instanceof Error ? err.message : "Failed to load agent"
          );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [name, client, setConfig]);

  const StepComponent = STEPS[currentStep - 1].component;

  if (loadError) {
    return (
      <div className="p-6 max-w-4xl mx-auto">
        <p className="text-red-400">Error loading agent: {loadError}</p>
        <Button variant="secondary" className="mt-4" onClick={() => navigate("/")}>
          Back to Dashboard
        </Button>
      </div>
    );
  }

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Step Indicator */}
      <div className="flex items-center gap-1 mb-8 overflow-x-auto pb-2">
        {STEPS.map((step, i) => {
          const stepNum = i + 1;
          const isActive = stepNum === currentStep;
          const isCompleted = stepNum < currentStep;
          return (
            <button
              key={step.label}
              onClick={() => setCurrentStep(stepNum)}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap ${
                isActive
                  ? "bg-cyan-500/20 text-cyan-400 border border-cyan-500/50"
                  : isCompleted
                    ? "bg-gray-800 text-green-400 border border-gray-700"
                    : "bg-gray-800/50 text-gray-500 border border-gray-700/50"
              }`}
            >
              <span
                className={`flex items-center justify-center w-6 h-6 rounded-full text-xs ${
                  isActive
                    ? "bg-cyan-500 text-white"
                    : isCompleted
                      ? "bg-green-500/30 text-green-400"
                      : "bg-gray-700 text-gray-500"
                }`}
              >
                {isCompleted ? "\u2713" : stepNum}
              </span>
              {step.label}
            </button>
          );
        })}
      </div>

      {/* Step Content */}
      <div className="min-h-[400px]">
        <StepComponent />
      </div>

      {/* Navigation */}
      <div className="flex items-center justify-between mt-8 pt-4 border-t border-gray-700">
        <div>
          {currentStep > 1 && (
            <Button
              variant="secondary"
              onClick={() => setCurrentStep((s) => s - 1)}
            >
              Back
            </Button>
          )}
        </div>
        <div className="flex gap-3">
          <Button
            variant="ghost"
            onClick={() => navigate("/canvas")}
          >
            Open in Canvas
          </Button>
          {currentStep < STEPS.length && (
            <Button onClick={() => setCurrentStep((s) => s + 1)}>Next</Button>
          )}
        </div>
      </div>
    </div>
  );
}
