import { cn } from "@/lib/utils";
import { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  className?: string;
}

export function Input({ label, error, className, id, ...rest }: InputProps) {
  const inputId = id ?? label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className="flex flex-col gap-1.5 w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-medium text-am-text-dim uppercase tracking-wide"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={cn(
          "w-full rounded-md bg-am-bg border border-am-border px-3 py-2 text-sm text-am-text placeholder:text-am-text-dim",
          "focus:outline-none focus:ring-2 focus:ring-am-cyan focus:border-transparent transition-all",
          error && "border-am-red focus:ring-am-red",
          className
        )}
        {...rest}
      />
      {error && <p className="text-xs text-am-red">{error}</p>}
    </div>
  );
}
