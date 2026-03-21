import { useConsoleStore } from "../../stores/console";
import { ConsoleLeftPanel } from "./ConsoleLeftPanel";
import { ConsoleCenterPanel } from "./ConsoleCenterPanel";
import { ConsoleRightPanel } from "./ConsoleRightPanel";
import { CompareView } from "./CompareView";

export function ConsoleShell() {
  const { runs, compareSelection } = useConsoleStore();

  const isComparing =
    compareSelection !== null && compareSelection[0] !== compareSelection[1];
  const compareRunA = isComparing
    ? runs.find((r) => r.id === compareSelection![0])
    : undefined;
  const compareRunB = isComparing
    ? runs.find((r) => r.id === compareSelection![1])
    : undefined;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] min-w-[1280px]">
      <ConsoleLeftPanel />
      {isComparing && compareRunA && compareRunB ? (
        <CompareView runA={compareRunA} runB={compareRunB} />
      ) : (
        <>
          <ConsoleCenterPanel />
          <ConsoleRightPanel />
        </>
      )}
    </div>
  );
}
