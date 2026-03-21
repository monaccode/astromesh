import { useCallback, useEffect, useMemo, useState, type MouseEvent } from "react";
import { useParams } from "react-router-dom";
import {
  ReactFlow,
  MiniMap,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeTypes,
  type OnSelectionChangeParams,
  type NodeChange,
  type EdgeChange,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useConnectionStore } from "../../stores/connection";
import { agentToNodes } from "../../utils/agent-to-nodes";
import { nodesToAgent } from "../../utils/nodes-to-agent";
import { appendToChain, nextStackPosition, removeNodeReconnect } from "../../utils/pipeline-graph";
import type { AgentConfig, AgentMeta } from "../../types/agent";
import type { AgentNodeData, PipelineNodeData } from "../../types/canvas";

import { AgentNode } from "./nodes/AgentNode";
import { ToolNode } from "./nodes/ToolNode";
import { ModelNode } from "./nodes/ModelNode";
import { GuardrailNode } from "./nodes/GuardrailNode";
import { MemoryNode } from "./nodes/MemoryNode";
import { PromptNode } from "./nodes/PromptNode";

import { Toolbox, type PipelinePreset } from "./panels/Toolbox";
import { PropertiesPanel } from "./panels/PropertiesPanel";
import { PipelinePropertiesPanel } from "./panels/PipelinePropertiesPanel";
import { Button } from "../ui/Button";

const NODE_TYPES: NodeTypes = {
  agent: AgentNode,
  tool: ToolNode,
  model: ModelNode,
  guardrail: GuardrailNode,
  memory: MemoryNode,
  prompt: PromptNode,
};

function mapPipelineNodes(
  raw: {
    id: string;
    type: string;
    position: { x: number; y: number };
    data: { label: string; category: string; config: Record<string, unknown> };
  }[],
) {
  return raw.map((n) => ({
    ...n,
    type: n.data.category,
  }));
}

const PIPELINE_NODE_TYPES = new Set([
  "tool",
  "model",
  "guardrail",
  "memory",
  "prompt",
]);

export function CanvasEditor() {
  const { name } = useParams<{ name?: string }>();
  const client = useConnectionStore((s) => s.client);
  const connected = useConnectionStore((s) => s.connected);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([] as Edge[]);

  const [viewMode, setViewMode] = useState<"macro" | "micro">("macro");
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [expandedBaseConfig, setExpandedBaseConfig] = useState<AgentConfig | null>(null);
  const [selectedNodeData, setSelectedNodeData] = useState<AgentNodeData | null>(null);
  const [selectedPipelineNodeId, setSelectedPipelineNodeId] = useState<string | null>(null);
  const [pipelineDirty, setPipelineDirty] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [agentConfigs, setAgentConfigs] = useState<Record<string, AgentConfig>>({});

  const selectedPipelineNode = useMemo(
    () => nodes.find((n) => n.id === selectedPipelineNodeId) ?? null,
    [nodes, selectedPipelineNodeId],
  );

  useEffect(() => {
    if (!name || !connected) return;
    client
      .getAgent(name)
      .then((config) => {
        setAgentConfigs((prev) => ({ ...prev, [name]: config }));
        setNodes([
          {
            id: `agent-${name}`,
            type: "agent",
            position: { x: 300, y: 200 },
            data: {
              name: config.metadata.name,
              displayName: config.spec.identity.display_name,
              status: "deployed" as const,
              pattern: config.spec.orchestration.pattern,
            },
          },
        ]);
        setEdges([]);
      })
      .catch(() => {
        /* agent not found or not connected */
      });
  }, [name, connected, client, setNodes, setEdges]);

  const handleNodesChange = useCallback(
    (changes: NodeChange<Node>[]) => {
      onNodesChange(changes);
      if (changes.some((c) => c.type !== "select")) {
        setPipelineDirty(true);
      }
    },
    [onNodesChange],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      onEdgesChange(changes);
      if (changes.length) {
        setPipelineDirty(true);
      }
    },
    [onEdgesChange],
  );

  const handleAddAgent = useCallback(
    (agent: AgentMeta) => {
      const id = `agent-${agent.name}-${Date.now()}`;
      const x = 200 + Math.random() * 300;
      const y = 150 + Math.random() * 200;
      setNodes((nds) => [
        ...nds,
        {
          id,
          type: "agent",
          position: { x, y },
          data: {
            name: agent.name,
            displayName: agent.name,
            status: agent.status,
            pattern: "unknown",
          },
        },
      ]);

      if (connected) {
        client
          .getAgent(agent.name)
          .then((config) => {
            setAgentConfigs((prev) => ({ ...prev, [agent.name]: config }));
            setNodes((nds) =>
              nds.map((n) =>
                n.id === id
                  ? {
                      ...n,
                      data: {
                        name: config.metadata.name,
                        displayName: config.spec.identity.display_name,
                        status: agent.status,
                        pattern: config.spec.orchestration.pattern,
                      },
                    }
                  : n,
              ),
            );
          })
          .catch(() => {
            /* ignore */
          });
      }
    },
    [client, connected, setNodes],
  );

  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }: OnSelectionChangeParams) => {
      if (viewMode === "micro") {
        if (selectedNodes.length === 1) {
          setSelectedPipelineNodeId(selectedNodes[0].id);
        } else {
          setSelectedPipelineNodeId(null);
        }
        setSelectedNodeData(null);
        return;
      }
      if (selectedNodes.length === 1 && selectedNodes[0].type === "agent") {
        setSelectedNodeData(selectedNodes[0].data as AgentNodeData);
      } else {
        setSelectedNodeData(null);
      }
      setSelectedPipelineNodeId(null);
    },
    [viewMode],
  );

  const onNodeDoubleClick = useCallback(
    (_event: MouseEvent, node: { type?: string; data: Record<string, unknown> }) => {
      if (node.type === "agent") {
        const agentName = (node.data as AgentNodeData).name;
        drillDown(agentName);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [agentConfigs],
  );

  const drillDown = useCallback(
    (agentName: string) => {
      const config = agentConfigs[agentName];
      if (!config) return;

      const { nodes: pipelineNodes, edges: pipelineEdges } = agentToNodes(config);
      setNodes(mapPipelineNodes(pipelineNodes));
      setEdges(pipelineEdges);
      setExpandedAgent(agentName);
      setExpandedBaseConfig(structuredClone(config));
      setViewMode("micro");
      setSelectedNodeData(null);
      setSelectedPipelineNodeId(null);
      setPipelineDirty(false);
      setSaveMessage(null);
    },
    [agentConfigs, setNodes, setEdges],
  );

  const backToMacro = useCallback(() => {
    setViewMode("macro");
    setExpandedAgent(null);
    setExpandedBaseConfig(null);
    setSelectedNodeData(null);
    setSelectedPipelineNodeId(null);
    setPipelineDirty(false);
    setSaveMessage(null);

    const macroNodes = Object.entries(agentConfigs).map(([agentName, config], i) => ({
      id: `agent-${agentName}`,
      type: "agent" as const,
      position: { x: 300 + (i % 3) * 300, y: 200 + Math.floor(i / 3) * 200 },
      data: {
        name: config.metadata.name,
        displayName: config.spec.identity.display_name,
        status: "deployed" as const,
        pattern: config.spec.orchestration.pattern,
      },
    }));
    setNodes(macroNodes);
    setEdges([]);
  }, [agentConfigs, setNodes, setEdges]);

  const handleExpandPipeline = useCallback(() => {
    if (selectedNodeData) {
      drillDown(selectedNodeData.name);
    }
  }, [selectedNodeData, drillDown]);

  const isSlotTaken = useCallback(
    (prefix: string) => nodes.some((n) => n.id.startsWith(prefix)),
    [nodes],
  );

  const appendPresetNode = useCallback(
    (built: {
      id: string;
      category: "tool" | "memory" | "guardrail";
      label: string;
      config: Record<string, unknown>;
    }) => {
      const pos = nextStackPosition(nodes);
      const newNode: Node = {
        id: built.id,
        type: built.category,
        position: pos,
        data: {
          label: built.label,
          category: built.category,
          config: built.config,
        },
      };
      const { nodes: nn, edges: ee } = appendToChain(nodes, edges, newNode);
      setNodes(nn);
      setEdges(ee);
      setPipelineDirty(true);
    },
    [nodes, edges, setNodes, setEdges],
  );

  const handleAddBuiltinTool = useCallback(
    (t: { name: string; description: string }) => {
      appendPresetNode({
        id: `tool-${t.name}-${Date.now()}`,
        category: "tool",
        label: t.name,
        config: {
          name: t.name,
          type: "internal",
          description: t.description,
          parameters: {},
        },
      });
    },
    [appendPresetNode],
  );

  const handleAddPreset = useCallback(
    (preset: PipelinePreset) => {
      appendPresetNode(preset.build());
    },
    [appendPresetNode],
  );

  const handleAddFallbackModel = useCallback(() => {
    const fb = expandedBaseConfig?.spec.model.fallback ?? {
      provider: "ollama",
      model: "llama3.1:8b",
      endpoint: "http://127.0.0.1:11434",
    };
    const pos = nextStackPosition(nodes);
    const newNode: Node = {
      id: "model-fallback",
      type: "model",
      position: pos,
      data: {
        label: `Fallback: ${fb.provider}/${fb.model}`,
        category: "model",
        config: { ...fb } as unknown as Record<string, unknown>,
      },
    };
    const { nodes: nn, edges: ee } = appendToChain(nodes, edges, newNode);
    setNodes(nn);
    setEdges(ee);
    setPipelineDirty(true);
  }, [expandedBaseConfig, nodes, edges, setNodes, setEdges]);

  const applyPipelineNode = useCallback(
    (id: string, data: PipelineNodeData) => {
      setNodes((nds) => nds.map((n) => (n.id === id ? { ...n, data: { ...data } } : n)));
      setPipelineDirty(true);
    },
    [setNodes],
  );

  const removePipelineNode = useCallback(
    (nodeId: string) => {
      const { nodes: nn, edges: ee } = removeNodeReconnect(nodes, edges, nodeId);
      setNodes(nn);
      setEdges(ee);
      setSelectedPipelineNodeId(null);
      setPipelineDirty(true);
    },
    [nodes, edges, setNodes, setEdges],
  );

  const savePipeline = useCallback(async () => {
    if (!expandedAgent || !expandedBaseConfig || !connected) return;
    setSaving(true);
    setSaveMessage(null);
    try {
      const snapshots = nodes
        .filter((n) => PIPELINE_NODE_TYPES.has(n.type ?? ""))
        .map((n) => ({
          id: n.id,
          data: n.data as PipelineNodeData,
        }));
      const merged = nodesToAgent(snapshots, expandedBaseConfig);
      await client.updateAgent(expandedAgent, merged);
      setExpandedBaseConfig(merged);
      setAgentConfigs((prev) => ({ ...prev, [expandedAgent]: merged }));
      setPipelineDirty(false);
      setSaveMessage("Saved");
      window.setTimeout(() => setSaveMessage(null), 2800);
    } catch (e) {
      setSaveMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }, [expandedAgent, expandedBaseConfig, connected, client, nodes]);

  const memoizedNodeTypes = useMemo(() => NODE_TYPES, []);

  const canAddFallbackModel = !nodes.some((n) => n.id === "model-fallback");

  return (
    <div className="flex h-full w-full" style={{ height: "calc(100vh - 64px)" }}>
      {viewMode === "macro" && <Toolbox onAddAgent={handleAddAgent} />}
      {viewMode === "micro" && (
        <Toolbox
          onAddAgent={handleAddAgent}
          micro={{
            isSlotTaken,
            onAddBuiltinTool: handleAddBuiltinTool,
            onAddPreset: handleAddPreset,
            onAddFallbackModel: handleAddFallbackModel,
            canAddFallbackModel,
          }}
        />
      )}

      <div className="flex-1 relative">
        {viewMode === "micro" && expandedAgent && (
          <div className="absolute top-3 left-3 z-10 flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="bg-gray-800 border border-gray-700 hover:bg-gray-700 text-gray-200 text-sm px-3 py-1.5 rounded-lg transition-colors"
              onClick={backToMacro}
            >
              &larr; Back to Overview
            </button>
            <span className="text-sm text-gray-400">
              Pipeline: <span className="text-gray-200 font-medium">{expandedAgent}</span>
            </span>
            {pipelineDirty && (
              <span className="text-xs text-amber-400/90">Unsaved changes</span>
            )}
            <Button
              variant="primary"
              className="text-sm py-1.5 px-3"
              disabled={!pipelineDirty || saving || !connected}
              onClick={() => void savePipeline()}
            >
              {saving ? "Saving…" : "Save pipeline"}
            </Button>
            {saveMessage && (
              <span
                className={`text-xs ${saveMessage === "Saved" ? "text-green-400" : "text-red-400"}`}
              >
                {saveMessage}
              </span>
            )}
          </div>
        )}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={viewMode === "micro" ? handleNodesChange : onNodesChange}
          onEdgesChange={viewMode === "micro" ? handleEdgesChange : onEdgesChange}
          onSelectionChange={onSelectionChange}
          onNodeDoubleClick={onNodeDoubleClick}
          nodeTypes={memoizedNodeTypes}
          fitView
          style={{ background: "#030712" }}
          proOptions={{ hideAttribution: true }}
        >
          <Controls className="!bg-gray-800 !border-gray-700 !rounded-lg [&>button]:!bg-gray-800 [&>button]:!border-gray-700 [&>button]:!text-gray-300 [&>button:hover]:!bg-gray-700" />
          <MiniMap
            className="!bg-gray-900 !border-gray-800 !rounded-lg"
            nodeColor="#374151"
            maskColor="rgba(0,0,0,0.6)"
          />
          <Background color="#1f2937" gap={20} />
        </ReactFlow>
      </div>

      {viewMode === "macro" && selectedNodeData && (
        <PropertiesPanel
          nodeData={selectedNodeData}
          onClose={() => setSelectedNodeData(null)}
          onExpandPipeline={handleExpandPipeline}
        />
      )}

      {viewMode === "micro" && selectedPipelineNode && (
        <PipelinePropertiesPanel
          node={selectedPipelineNode}
          onApply={applyPipelineNode}
          onRemove={removePipelineNode}
          onClose={() => setSelectedPipelineNodeId(null)}
        />
      )}
    </div>
  );
}
