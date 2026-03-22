import type { SpanTreeNode } from "../../utils/trace-tree";

interface SpanChipsProps {
  node: SpanTreeNode;
  onChipClick: (tab: string) => void;
}

interface ChipDef {
  label: string;
  tab: string;
  show: boolean;
  color: string;
}

export function SpanChips({ node, onChipClick }: SpanChipsProps) {
  const attrs = node.attributes;
  const chips: ChipDef[] = [
    {
      label: "\u{1F4AC}",
      tab: "output",
      show: typeof attrs.response === "string" && attrs.response.length > 0,
      color: "bg-amber-500/20 text-amber-400",
    },
    {
      label: "\u{1F527}",
      tab: "toolcalls",
      show: Array.isArray(attrs.tool_calls) && attrs.tool_calls.length > 0,
      color: "bg-orange-500/20 text-orange-400",
    },
    {
      label: "\u2705",
      tab: "output",
      show: node.name.startsWith("tool.") && node.status === "ok",
      color: "bg-green-500/20 text-green-400",
    },
    {
      label: "\u{1F4CB}",
      tab: "events",
      show: node.events.length > 0,
      color: "bg-blue-500/20 text-blue-400",
    },
    {
      label: "\u26A0\uFE0F",
      tab: "overview",
      show: node.status === "error",
      color: "bg-red-500/20 text-red-400",
    },
    {
      label: "\u{1F6E1}\uFE0F",
      tab: "guardrails",
      show: node.events.some((e) => e.name === "guardrail"),
      color: "bg-purple-500/20 text-purple-400",
    },
  ];

  const visible = chips.filter((c) => c.show);
  if (visible.length === 0) return null;

  return (
    <span className="inline-flex gap-0.5 ml-1">
      {visible.map((chip, i) => (
        <span
          key={i}
          className={`${chip.color} text-[8px] px-1 rounded cursor-pointer hover:opacity-80`}
          title={`View ${chip.tab}`}
          onClick={(e) => {
            e.stopPropagation();
            onChipClick(chip.tab);
          }}
        >
          {chip.label}
        </span>
      ))}
    </span>
  );
}
