import type { Edge, Node } from "@xyflow/react";

/** Last node in the linear chain (prefers bottom-most sink). */
export function findTailNodeId(nodes: Node[], edges: Edge[]): string | null {
  if (!nodes.length) return null;
  const hasOutgoing = new Set(edges.map((e) => e.source));
  const sinks = nodes.filter((n) => !hasOutgoing.has(n.id));
  if (sinks.length === 1) return sinks[0].id;
  if (sinks.length > 1) {
    const sorted = [...sinks].sort((a, b) => a.position.y - b.position.y);
    return sorted[sorted.length - 1].id;
  }
  const sorted = [...nodes].sort((a, b) => b.position.y - a.position.y);
  return sorted[0]?.id ?? null;
}

export function nextStackPosition(nodes: Node[]): { x: number; y: number } {
  if (!nodes.length) return { x: 250, y: 0 };
  const maxY = Math.max(...nodes.map((n) => n.position.y));
  return { x: 250, y: maxY + 120 };
}

export function appendToChain(
  nodes: Node[],
  edges: Edge[],
  newNode: Node,
): { nodes: Node[]; edges: Edge[] } {
  const tail = findTailNodeId(nodes, edges);
  const nextEdges = [...edges];
  if (tail && tail !== newNode.id) {
    nextEdges.push({
      id: `${tail}-${newNode.id}`,
      source: tail,
      target: newNode.id,
    });
  }
  return { nodes: [...nodes, newNode], edges: nextEdges };
}

/** Remove a node and reconnect single predecessor to single successor when possible. */
export function removeNodeReconnect(
  nodes: Node[],
  edges: Edge[],
  nodeId: string,
): { nodes: Node[]; edges: Edge[] } {
  const incoming = edges.filter((e) => e.target === nodeId);
  const outgoing = edges.filter((e) => e.source === nodeId);
  let nextEdges = edges.filter((e) => e.source !== nodeId && e.target !== nodeId);
  if (incoming.length === 1 && outgoing.length === 1) {
    nextEdges.push({
      id: `${incoming[0].source}-${outgoing[0].target}`,
      source: incoming[0].source,
      target: outgoing[0].target,
    });
  }
  return { nodes: nodes.filter((n) => n.id !== nodeId), edges: nextEdges };
}
