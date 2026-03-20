import { type HTMLAttributes } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hoverable?: boolean;
}

export function Card({
  hoverable = false,
  className = "",
  ...props
}: CardProps) {
  return (
    <div
      className={`bg-gray-800 border border-gray-700 rounded-xl p-4 ${
        hoverable ? "hover:border-cyan-500/50 cursor-pointer transition-colors" : ""
      } ${className}`}
      {...props}
    />
  );
}
