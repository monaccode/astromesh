import type { Node, Edge } from "@xyflow/react";

export type AgentNodeData = {
  name: string;
  displayName: string;
  status: "draft" | "deployed" | "paused";
  pattern: string;
};

export type PipelineNodeData = {
  label: string;
  category: "guardrail" | "memory" | "prompt" | "model" | "tool";
  config: Record<string, unknown>;
};

export type ForgeNode = Node<AgentNodeData, "agent"> | Node<PipelineNodeData, "pipeline">;
export type ForgeEdge = Edge;
