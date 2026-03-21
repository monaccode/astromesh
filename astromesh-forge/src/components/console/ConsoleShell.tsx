import { ConsoleLeftPanel } from "./ConsoleLeftPanel";
import { ConsoleCenterPanel } from "./ConsoleCenterPanel";
import { ConsoleRightPanel } from "./ConsoleRightPanel";

export function ConsoleShell() {
  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-w-[1280px]">
      <ConsoleLeftPanel />
      <ConsoleCenterPanel />
      <ConsoleRightPanel />
    </div>
  );
}
