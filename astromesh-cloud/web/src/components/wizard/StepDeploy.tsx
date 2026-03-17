"use client";

import { useWizardStore } from "@/lib/store";
import { cn } from "@/lib/utils";

export function StepDeploy() {
  const config = useWizardStore((s) => s.config);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-lg font-semibold text-am-text">Deploy</h2>
        <p className="mt-1 text-sm text-am-text-dim">
          Review your configuration and deploy your agent.
        </p>
      </div>

      <div className="rounded-xl border border-am-cyan/30 bg-am-cyan-dim p-6 text-center space-y-3">
        <div className="flex h-12 w-12 mx-auto items-center justify-center rounded-full bg-am-cyan/20 border border-am-cyan/30 text-2xl">
          🚀
        </div>
        <p className="text-sm font-semibold text-am-cyan">Ready to deploy</p>
        <p className="text-xs text-am-text-dim">
          Agent{" "}
          <span className="font-mono text-am-text">
            {config.agentName || "your-agent"}
          </span>{" "}
          will be created with model{" "}
          <span className="font-mono text-am-text">{config.model}</span> and{" "}
          {config.tools.length} tool{config.tools.length !== 1 ? "s" : ""}{" "}
          enabled.
        </p>
      </div>

      <p className="text-xs text-am-text-dim text-center">
        Full deploy step coming in a future task. Click{" "}
        <span className="text-am-cyan">Deploy</span> to submit.
      </p>
    </div>
  );
}
