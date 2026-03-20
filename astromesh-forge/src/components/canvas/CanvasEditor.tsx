import { useCallback, useEffect, useMemo, useState } from "react";
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
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import { useConnectionStore } from "../../stores/connection";
import { agentToNodes } from "../../utils/agent-to-nodes";
import type { AgentConfig, AgentMeta } from "../../types/agent";
import type { AgentNodeData } from "../../types/canvas";

import { AgentNode } from "./nodes/AgentNode";
import { ToolNode } from "./nodes/ToolNode";
import { ModelNode } from "./nodes/ModelNode";
import { GuardrailNode } from "./nodes/GuardrailNode";
import { MemoryNode } from "./nodes/MemoryNode";
import { PromptNode } from "./nodes/PromptNode";

import { Toolbox } from "./panels/Toolbox";
import { PropertiesPanel } from "./panels/PropertiesPanel";

const NODE_TYPES: NodeTypes = {
  agent: AgentNode,
  tool: ToolNode,
  model: ModelNode,
  guardrail: GuardrailNode,
  memory: MemoryNode,
  prompt: PromptNode,
};

// Map pipeline categories to custom node types
function mapPipelineNodes(
  raw: { id: string; type: string; position: { x: number; y: number }; data: { label: string; category: string; config: Record<string, unknown> } }[],
) {
  return raw.map((n) => ({
    ...n,
    type: n.data.category, // "tool" | "model" | "guardrail" | "memory" | "prompt"
  }));
}

export function CanvasEditor() {
  const { name } = useParams<{ name?: string }>();
  const client = useConnectionStore((s) => s.client);
  const connected = useConnectionStore((s) => s.connected);

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([] as Node[]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([] as Edge[]);

  const [viewMode, setViewMode] = useState<"macro" | "micro">("macro");
  const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
  const [selectedNodeData, setSelectedNodeData] = useState<AgentNodeData | null>(null);

  // Cache loaded agent configs for drill-down
  const [agentConfigs, setAgentConfigs] = useState<Record<string, AgentConfig>>({});

  // Load single agent from URL param
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

  // Add agent from toolbox
  const handleAddAgent = useCallback(
    (agent: AgentMeta) => {
      const id = `agent-${agent.name}-${Date.now()}`;
      // Place at a somewhat random position to avoid stacking
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

      // Load full config for drill-down later
      if (connected) {
        client.getAgent(agent.name).then((config) => {
          setAgentConfigs((prev) => ({ ...prev, [agent.name]: config }));
          // Update the node with real data
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
        }).catch(() => {/* ignore */});
      }
    },
    [client, connected, setNodes],
  );

  // Selection change handler
  const onSelectionChange = useCallback(
    ({ nodes: selectedNodes }: OnSelectionChangeParams) => {
      if (selectedNodes.length === 1 && selectedNodes[0].type === "agent") {
        setSelectedNodeData(selectedNodes[0].data as AgentNodeData);
      } else {
        setSelectedNodeData(null);
      }
    },
    [],
  );

  // Double-click on node triggers drill-down
  const onNodeDoubleClick = useCallback(
    (_event: React.MouseEvent, node: { type?: string; data: Record<string, unknown> }) => {
      if (node.type === "agent") {
        const agentName = (node.data as AgentNodeData).name;
        drillDown(agentName);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [agentConfigs],
  );

  // Drill down to micro view
  const drillDown = useCallback(
    (agentName: string) => {
      const config = agentConfigs[agentName];
      if (!config) return;

      const { nodes: pipelineNodes, edges: pipelineEdges } = agentToNodes(config);
      setNodes(mapPipelineNodes(pipelineNodes));
      setEdges(pipelineEdges);
      setExpandedAgent(agentName);
      setViewMode("micro");
      setSelectedNodeData(null);
    },
    [agentConfigs, setNodes, setEdges],
  );

  // Back to macro view
  const backToMacro = useCallback(() => {
    setViewMode("macro");
    setExpandedAgent(null);
    setSelectedNodeData(null);

    // Rebuild macro nodes from cached configs
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

  // Expand pipeline from properties panel
  const handleExpandPipeline = useCallback(() => {
    if (selectedNodeData) {
      drillDown(selectedNodeData.name);
    }
  }, [selectedNodeData, drillDown]);

  const memoizedNodeTypes = useMemo(() => NODE_TYPES, []);

  return (
    <div className="flex h-full w-full" style={{ height: "calc(100vh - 64px)" }}>
      {/* Left: Toolbox (macro only) */}
      {viewMode === "macro" && <Toolbox onAddAgent={handleAddAgent} />}

      {/* Center: Canvas */}
      <div className="flex-1 relative">
        {/* Micro view header */}
        {viewMode === "micro" && expandedAgent && (
          <div className="absolute top-3 left-3 z-10 flex items-center gap-3">
            <button
              className="bg-gray-800 border border-gray-700 hover:bg-gray-700 text-gray-200 text-sm px-3 py-1.5 rounded-lg transition-colors"
              onClick={backToMacro}
            >
              &larr; Back to Overview
            </button>
            <span className="text-sm text-gray-400">
              Pipeline: <span className="text-gray-200 font-medium">{expandedAgent}</span>
            </span>
          </div>
        )}

        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onSelectionChange={onSelectionChange}
          onNodeDoubleClick={onNodeDoubleClick}
          nodeTypes={memoizedNodeTypes}
          fitView
          style={{ background: "#030712" }}
          proOptions={{ hideAttribution: true }}
        >
          <Controls
            className="!bg-gray-800 !border-gray-700 !rounded-lg [&>button]:!bg-gray-800 [&>button]:!border-gray-700 [&>button]:!text-gray-300 [&>button:hover]:!bg-gray-700"
          />
          <MiniMap
            className="!bg-gray-900 !border-gray-800 !rounded-lg"
            nodeColor="#374151"
            maskColor="rgba(0,0,0,0.6)"
          />
          <Background color="#1f2937" gap={20} />
        </ReactFlow>
      </div>

      {/* Right: Properties panel (macro only, when node selected) */}
      {viewMode === "macro" && selectedNodeData && (
        <PropertiesPanel
          nodeData={selectedNodeData}
          onClose={() => setSelectedNodeData(null)}
          onExpandPipeline={handleExpandPipeline}
        />
      )}
    </div>
  );
}
