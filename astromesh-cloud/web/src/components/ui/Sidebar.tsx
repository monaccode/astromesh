"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

interface NavLink {
  label: string;
  href: string;
  icon: string;
}

const NAV_LINKS: NavLink[] = [
  { label: "Agents", href: "/agents", icon: "⬡" },
  { label: "Studio", href: "/studio", icon: "✦" },
  { label: "Usage", href: "/usage", icon: "⌀" },
  { label: "Settings", href: "/settings", icon: "⚙" },
];

interface SidebarProps {
  orgSlug: string;
  orgName: string;
}

export function Sidebar({ orgSlug, orgName }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside className="fixed inset-y-0 left-0 w-56 flex flex-col border-r border-am-border bg-am-bg z-30">
      <div className="px-5 py-5">
        <span className="font-mono text-sm font-bold tracking-widest text-am-cyan">
          ASTROMESH
        </span>
      </div>

      <nav className="flex-1 px-3 space-y-0.5">
        {NAV_LINKS.map(({ label, href, icon }) => {
          const active = pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-all",
                active
                  ? "bg-am-cyan-dim text-am-cyan font-medium"
                  : "text-am-text-dim hover:bg-am-surface hover:text-am-text"
              )}
            >
              <span className="w-4 text-center leading-none">{icon}</span>
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-am-border px-5 py-4">
        <p className="text-xs text-am-text-dim truncate">{orgName}</p>
      </div>
    </aside>
  );
}
