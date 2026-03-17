import { cn } from "@/lib/utils";

interface CardProps {
  children: React.ReactNode;
  className?: string;
  hoverable?: boolean;
}

export function Card({ children, className, hoverable }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-xl bg-am-surface border border-am-border p-5 transition-all",
        hoverable &&
          "hover:border-am-border-hover hover:shadow-[0_0_16px_rgba(0,212,255,0.12)] cursor-pointer",
        className
      )}
    >
      {children}
    </div>
  );
}
