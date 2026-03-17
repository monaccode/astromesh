import { cn } from "@/lib/utils";

interface ToggleProps {
  checked: boolean;
  onChange: (value: boolean) => void;
  label?: string;
  disabled?: boolean;
}

export function Toggle({ checked, onChange, label, disabled }: ToggleProps) {
  return (
    <label className={cn("inline-flex items-center gap-3 cursor-pointer", disabled && "opacity-40 cursor-not-allowed")}>
      <button
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "relative h-6 w-11 rounded-full border transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-am-cyan",
          checked
            ? "bg-am-cyan border-am-cyan"
            : "bg-am-bg border-am-border"
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-am-bg transition-transform",
            checked && "translate-x-5 bg-am-bg"
          )}
        />
      </button>
      {label && <span className="text-sm text-am-text">{label}</span>}
    </label>
  );
}
