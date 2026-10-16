import { render, fireEvent, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import yaml from "js-yaml";
import { useAgentEditorStore } from "../../../stores/agent";
import { StepModel } from "../StepModel";
import { StepOrchestration } from "../StepOrchestration";
import { StepPrompts } from "../StepPrompts";
import type { AgentConfig } from "../../../types/agent";

const CFG = yaml.load(`
apiVersion: astromesh/v1
kind: Agent
metadata: {name: w, version: 1.0.0}
spec:
  identity: {display_name: W, description: d}
  model:
    default: {candidates: [{source: ollama, model: a, context_window: 4096}], strategy: cost_optimized}
    roles: {planner: {candidates: [{source: litellm, model: x/y}], strategy: quality_first}}
  prompts: {system: hi, context: "{{ prefetch.t }}"}
  orchestration: {pattern: pipeline, max_iterations: 3, stages: [a, b], role_map: {plan: planner}}
  prefetch: [{tool: clock, as: t}]
  chain: {steps: [{agent: b}]}
`) as AgentConfig;

const cfg = () => useAgentEditorStore.getState().config;

describe("wizard on a core 0.70 manifest", () => {
  beforeEach(() => useAgentEditorStore.getState().setConfig(structuredClone(CFG)));

  it("StepModel renders per-role models and edits a role without losing others", () => {
    render(<StepModel />);
    expect(screen.getByText("Role: planner")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Model", { selector: "#default\\ candidate\\ 1-model" }), {
      target: { value: "b" },
    });
    expect(cfg().spec.model.default?.candidates[0]).toEqual({ source: "ollama", model: "b", context_window: 4096 });
    expect(cfg().spec.model.roles).toEqual(CFG.spec.model.roles);
  });

  it("StepOrchestration edits keep untouched sections and YAML sections apply on blur", () => {
    render(<StepOrchestration />);
    fireEvent.change(screen.getByLabelText("Max Iterations"), { target: { value: "7" } });
    expect(cfg().spec.orchestration).toEqual({ ...CFG.spec.orchestration, max_iterations: 7 });
    expect(cfg().spec.chain).toEqual(CFG.spec.chain);
    const prefetch = screen.getByLabelText("prefetch");
    fireEvent.change(prefetch, { target: { value: "- {tool: clock, as: now}\n" } });
    fireEvent.blur(prefetch);
    expect(cfg().spec.prefetch).toEqual([{ tool: "clock", as: "now" }]);
    fireEvent.change(prefetch, { target: { value: "" } });
    fireEvent.blur(prefetch);
    expect("prefetch" in cfg().spec).toBe(false);
  });

  it("StepPrompts edits prompts.context", () => {
    render(<StepPrompts />);
    const ctx = screen.getByDisplayValue("{{ prefetch.t }}");
    fireEvent.change(ctx, { target: { value: "" } });
    expect(cfg().spec.prompts).toEqual({ system: "hi" });
  });
});
