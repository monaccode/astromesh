type Variant = "default" | "success" | "warning" | "danger";

interface BadgeProps {
  variant?: Variant;
  children: React.ReactNode;
}

const variants: Record<Variant, string> = {
  default: "bg-gray-700 text-gray-300",
  success: "bg-green-500/20 text-green-400",
  warning: "bg-yellow-500/20 text-yellow-400",
  danger: "bg-red-500/20 text-red-400",
};

export function Badge({ variant = "default", children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${variants[variant]}`}
    >
      {children}
    </span>
  );
}
