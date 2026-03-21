import type { LucideIcon } from "lucide-react";

type Variant = "default" | "success" | "warning" | "danger";

interface BadgeProps {
  variant?: Variant;
  icon?: LucideIcon;
  children: React.ReactNode;
}

const variants: Record<Variant, string> = {
  default: "bg-gray-700 text-gray-300",
  success: "bg-green-500/20 text-green-400",
  warning: "bg-yellow-500/20 text-yellow-400",
  danger: "bg-red-500/20 text-red-400",
};

export function Badge({ variant = "default", icon: Icon, children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center ${Icon ? "gap-1" : ""} px-2 py-0.5 rounded-full text-xs font-medium ${variants[variant]}`}
    >
      {Icon && <Icon size={14} />}
      {children}
    </span>
  );
}
