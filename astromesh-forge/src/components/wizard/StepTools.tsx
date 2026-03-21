import { useEffect, useState } from "react";
import {
  DndContext,
  type DragEndEvent,
  DragOverlay,
  type DragStartEvent,
  useDroppable,
} from "@dnd-kit/core";
import {
  SortableContext,
  useSortable,
  verticalListSortingStrategy,
  arrayMove,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { useAgentEditorStore } from "../../stores/agent";
import { useConnectionStore } from "../../stores/connection";
import { Badge } from "../ui/Badge";
import { Card } from "../ui/Card";
import type { ToolConfig } from "../../types/agent";

interface AvailableTool {
  name: string;
  description: string;
}

function DraggableAvailableTool({ tool }: { tool: AvailableTool }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } =
    useSortable({ id: `available-${tool.name}` });

  const style = {
    transform: CSS.Translate.toString(transform),
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <Card className="cursor-grab active:cursor-grabbing">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-gray-100">{tool.name}</p>
            <p className="text-xs text-gray-400">{tool.description}</p>
          </div>
          <Badge>available</Badge>
        </div>
      </Card>
    </div>
  );
}

function SortableAgentTool({
  tool,
  onRemove,
}: {
  tool: ToolConfig;
  onRemove: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: `agent-${tool.name}` });

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <Card className="cursor-grab active:cursor-grabbing">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium text-gray-100">{tool.name}</p>
            <Badge variant="success">{tool.type}</Badge>
          </div>
          <div className="flex items-center gap-1">
            <button
              className="text-gray-400 hover:text-gray-200 text-xs px-2 py-1"
              onClick={(e) => {
                e.stopPropagation();
                setExpanded(!expanded);
              }}
            >
              {expanded ? "Collapse" : "Expand"}
            </button>
            <button
              className="text-red-400 hover:text-red-300 text-xs px-2 py-1"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
            >
              Remove
            </button>
          </div>
        </div>
        {expanded && tool.parameters && (
          <div className="mt-3 pt-3 border-t border-gray-700">
            <p className="text-xs text-gray-400 mb-2">Parameters:</p>
            {Object.entries(tool.parameters).map(([key, param]) => (
              <div key={key} className="text-xs text-gray-300 mb-1">
                <span className="text-cyan-400">{key}</span>
                <span className="text-gray-500"> ({param.type})</span>
                {param.description && (
                  <span className="text-gray-400"> - {param.description}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function DroppableArea({
  id,
  children,
}: {
  id: string;
  children: React.ReactNode;
}) {
  const { setNodeRef } = useDroppable({ id });
  return (
    <div ref={setNodeRef} className="min-h-[200px]">
      {children}
    </div>
  );
}

export function StepTools() {
  const config = useAgentEditorStore((s) => s.config);
  const updateSpec = useAgentEditorStore((s) => s.updateSpec);
  const client = useConnectionStore((s) => s.client);
  const connected = useConnectionStore((s) => s.connected);

  const [availableTools, setAvailableTools] = useState<AvailableTool[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);

  const agentTools = config.spec.tools || [];

  useEffect(() => {
    if (!connected) return;
    setLoading(true);
    client
      .listTools()
      .then(setAvailableTools)
      .catch(() => setAvailableTools([]))
      .finally(() => setLoading(false));
  }, [client, connected]);

  // Filter out tools already added to the agent
  const agentToolNames = new Set(agentTools.map((t) => t.name));
  const filteredAvailable = availableTools.filter(
    (t) => !agentToolNames.has(t.name)
  );

  function handleDragStart(event: DragStartEvent) {
    setActiveId(event.active.id as string);
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveId(null);
    const { active, over } = event;
    if (!over) return;

    const activeIdStr = active.id as string;
    const overIdStr = over.id as string;

    // Dragging from available to agent area
    if (activeIdStr.startsWith("available-") && (overIdStr === "agent-tools-drop" || overIdStr.startsWith("agent-"))) {
      const toolName = activeIdStr.replace("available-", "");
      const tool = availableTools.find((t) => t.name === toolName);
      if (tool && !agentToolNames.has(toolName)) {
        const newTool: ToolConfig = {
          name: tool.name,
          type: "internal",
          description: tool.description,
        };
        updateSpec("tools", [...agentTools, newTool]);
      }
      return;
    }

    // Reordering within agent tools
    if (activeIdStr.startsWith("agent-") && overIdStr.startsWith("agent-")) {
      const oldName = activeIdStr.replace("agent-", "");
      const newName = overIdStr.replace("agent-", "");
      const oldIndex = agentTools.findIndex((t) => t.name === oldName);
      const newIndex = agentTools.findIndex((t) => t.name === newName);
      if (oldIndex !== -1 && newIndex !== -1 && oldIndex !== newIndex) {
        updateSpec("tools", arrayMove(agentTools, oldIndex, newIndex));
      }
    }
  }

  function removeTool(name: string) {
    updateSpec(
      "tools",
      agentTools.filter((t) => t.name !== name)
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-gray-100">Tools</h2>

      <DndContext onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Available Tools */}
          <div>
            <h3 className="text-md font-medium text-gray-200 mb-3">
              Available Tools
            </h3>
            {loading ? (
              <div className="space-y-2">
                <div className="h-14 bg-gray-700 animate-pulse rounded-xl" />
                <div className="h-14 bg-gray-700 animate-pulse rounded-xl" />
                <div className="h-14 bg-gray-700 animate-pulse rounded-xl" />
              </div>
            ) : !connected ? (
              <p className="text-sm text-gray-500">
                Connect to a node to see available tools.
              </p>
            ) : filteredAvailable.length === 0 ? (
              <p className="text-sm text-gray-500">
                No additional tools available.
              </p>
            ) : (
              <SortableContext
                items={filteredAvailable.map((t) => `available-${t.name}`)}
                strategy={verticalListSortingStrategy}
              >
                <div className="space-y-2">
                  {filteredAvailable.map((tool) => (
                    <DraggableAvailableTool key={tool.name} tool={tool} />
                  ))}
                </div>
              </SortableContext>
            )}
          </div>

          {/* Agent Tools */}
          <div>
            <h3 className="text-md font-medium text-gray-200 mb-3">
              Agent Tools
            </h3>
            <DroppableArea id="agent-tools-drop">
              {agentTools.length === 0 ? (
                <div className="border-2 border-dashed border-gray-700 rounded-xl p-8 text-center text-gray-500 text-sm">
                  Drag tools here to add them to your agent
                </div>
              ) : (
                <SortableContext
                  items={agentTools.map((t) => `agent-${t.name}`)}
                  strategy={verticalListSortingStrategy}
                >
                  <div className="space-y-2">
                    {agentTools.map((tool) => (
                      <SortableAgentTool
                        key={tool.name}
                        tool={tool}
                        onRemove={() => removeTool(tool.name)}
                      />
                    ))}
                  </div>
                </SortableContext>
              )}
            </DroppableArea>
          </div>
        </div>

        <DragOverlay>
          {activeId ? (
            <Card className="opacity-80 shadow-lg shadow-cyan-500/20">
              <p className="text-sm font-medium text-gray-100">
                {activeId.replace(/^(available|agent)-/, "")}
              </p>
            </Card>
          ) : null}
        </DragOverlay>
      </DndContext>
    </div>
  );
}
