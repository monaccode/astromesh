import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "danger";
type Size = "sm" | "md";

interface ButtonProps {
  variant?: Variant;
  size?: Size;
  disabled?: boolean;
  loading?: boolean;
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<Variant, string> = {
  primary:
    "bg-am-cyan text-am-bg font-semibold hover:opacity-90",
  secondary:
    "border border-am-cyan text-am-cyan bg-transparent hover:bg-am-cyan-dim",
  danger:
    "bg-am-red text-white font-semibold hover:opacity-90",
};

const sizeClasses: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs rounded",
  md: "px-5 py-2.5 text-sm rounded-md",
};

export function Button({
  variant = "primary",
  size = "md",
  disabled,
  loading,
  onClick,
  children,
  className,
}: ButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(
        "inline-flex items-center justify-center gap-2 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-am-cyan",
        variantClasses[variant],
        sizeClasses[size],
        (disabled || loading) && "opacity-40 cursor-not-allowed",
        className
      )}
    >
      {loading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  );
}
