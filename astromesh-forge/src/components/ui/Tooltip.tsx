import type { ReactNode } from "react";

interface TooltipProps {
  text: string;
  children: ReactNode;
  position?: "top" | "bottom";
}

const positions = {
  top: "bottom-full left-1/2 -translate-x-1/2 mb-1.5",
  bottom: "top-full left-1/2 -translate-x-1/2 mt-1.5",
};

export function Tooltip({ text, children, position = "top" }: TooltipProps) {
  return (
    <span className="relative group inline-flex">
      {children}
      <span
        className={`absolute ${positions[position]} invisible group-hover:visible opacity-0 group-hover:opacity-100 transition-opacity bg-gray-700 text-gray-200 text-xs px-2 py-1 rounded whitespace-nowrap pointer-events-none z-50`}
      >
        {text}
      </span>
    </span>
  );
}
