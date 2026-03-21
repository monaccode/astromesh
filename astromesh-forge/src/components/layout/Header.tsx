import { useConnectionStore } from "../../stores/connection";
import { Link } from "react-router-dom";

export function Header() {
  const { connected, checking, nodeUrl } = useConnectionStore();

  return (
    <header className="h-14 bg-gray-900 border-b border-gray-800 flex items-center px-4 justify-between">
      <div className="flex items-center gap-6">
        <Link to="/" className="text-cyan-400 font-bold text-lg">
          Astromesh Forge
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <Link
            to="/"
            className="text-gray-400 hover:text-gray-100 transition-colors"
          >
            Dashboard
          </Link>
          <Link
            to="/templates"
            className="text-gray-400 hover:text-gray-100 transition-colors"
          >
            Templates
          </Link>
          <Link
            to="/console"
            className="text-gray-400 hover:text-gray-100 transition-colors"
          >
            Console
          </Link>
        </nav>
      </div>
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <span
          className={`w-2 h-2 rounded-full ${
            checking
              ? "bg-yellow-400 animate-pulse"
              : connected
                ? "bg-green-400"
                : "bg-red-400"
          }`}
        />
        <span>{nodeUrl}</span>
      </div>
    </header>
  );
}
