import { cn } from "@/lib/utils";

export type AgentStatusValue = "draft" | "deployed" | "paused";

interface AgentStatusProps {
  status: AgentStatusValue;
  pulse?: boolean;
  className?: string;
}

const statusConfig: Record<
  AgentStatusValue,
  { label: string; classes: string }
> = {
  draft: {
    label: "Draft",
    classes: "border border-white/20 text-am-text-dim bg-white/5",
  },
  deployed: {
    label: "Deployed",
    classes: "border border-am-green/40 text-am-green bg-am-green/10",
  },
  paused: {
    label: "Paused",
    classes: "border border-am-amber/40 text-am-amber bg-am-amber/10",
  },
};

export function AgentStatus({ status, pulse = false, className }: AgentStatusProps) {
  const { label, classes } = statusConfig[status];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        classes,
        className
      )}
    >
      {status === "deployed" && pulse && (
        <span className="relative flex h-2 w-2 shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-am-green opacity-50" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-am-green" />
        </span>
      )}
      {label}
    </span>
  );
}
