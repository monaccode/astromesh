import { cn } from "@/lib/utils";

type BadgeVariant = "draft" | "deployed" | "paused" | "coming-soon";

interface BadgeProps {
  variant: BadgeVariant;
  children: React.ReactNode;
  pulse?: boolean;
}

const variantClasses: Record<BadgeVariant, string> = {
  draft: "bg-white/5 text-am-text-dim border border-white/10",
  deployed: "bg-am-green/10 text-am-green border border-am-green/20",
  paused: "bg-am-amber/10 text-am-amber border border-am-amber/20",
  "coming-soon": "bg-white/3 text-am-text-dim/50 border border-white/5",
};

export function Badge({ variant, children, pulse }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant]
      )}
    >
      {variant === "deployed" && pulse && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-am-green opacity-50" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-am-green" />
        </span>
      )}
      {children}
    </span>
  );
}
