import { useConnectionStore } from "../../stores/connection";
import { Link, useLocation } from "react-router-dom";
import {
  Hexagon,
  LayoutDashboard,
  BookTemplate,
  Terminal,
  Wifi,
  WifiOff,
  Loader2,
} from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { to: "/templates", label: "Templates", icon: BookTemplate },
  { to: "/console", label: "Console", icon: Terminal },
];

export function Header() {
  const { connected, checking, nodeUrl } = useConnectionStore();
  const { pathname } = useLocation();

  return (
    <header className="h-14 bg-gray-900 border-b border-gray-800 flex items-center px-4 justify-between">
      <div className="flex items-center gap-6">
        <Link to="/" className="flex items-center gap-2 text-cyan-400 font-bold text-lg">
          <Hexagon size={20} />
          Astromesh Forge
        </Link>
        <nav className="flex items-center gap-1 text-sm">
          {navItems.map(({ to, label, icon: Icon, exact }) => {
            const active = exact ? pathname === to : pathname.startsWith(to);
            return (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-colors ${
                  active
                    ? "text-cyan-400 bg-cyan-500/10"
                    : "text-gray-400 hover:text-gray-100 hover:bg-gray-800"
                }`}
              >
                <Icon size={16} />
                {label}
              </Link>
            );
          })}
        </nav>
      </div>
      <div className="flex items-center gap-2 text-sm text-gray-400">
        {checking ? (
          <Loader2 size={16} className="text-yellow-400 animate-spin" />
        ) : connected ? (
          <Wifi size={16} className="text-green-400" />
        ) : (
          <WifiOff size={16} className="text-red-400" />
        )}
        <span>{nodeUrl}</span>
      </div>
    </header>
  );
}
