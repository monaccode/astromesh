import { type ButtonHTMLAttributes } from "react";
import type { LucideIcon } from "lucide-react";

type Variant = "primary" | "secondary" | "danger" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: LucideIcon;
  iconRight?: LucideIcon;
}

const variants: Record<Variant, string> = {
  primary: "bg-cyan-500 hover:bg-cyan-600 text-white",
  secondary: "bg-gray-700 hover:bg-gray-600 text-gray-100",
  danger: "bg-red-600 hover:bg-red-700 text-white",
  ghost: "bg-transparent hover:bg-gray-800 text-gray-300",
};

export function Button({
  variant = "primary",
  className = "",
  icon: Icon,
  iconRight: IconRight,
  children,
  ...props
}: ButtonProps) {
  const hasIcon = Icon || IconRight;
  const iconOnly = hasIcon && !children;
  const padding = iconOnly ? "p-2" : "px-4 py-2";
  const flex = hasIcon ? "inline-flex items-center gap-2" : "";

  return (
    <button
      className={`${padding} rounded-lg font-medium transition-colors disabled:opacity-50 ${flex} ${variants[variant]} ${className}`}
      {...props}
    >
      {Icon && <Icon size={16} />}
      {children}
      {IconRight && <IconRight size={16} />}
    </button>
  );
}
