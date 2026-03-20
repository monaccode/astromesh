import { useRef } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "../ui/Card";
import { useAgentEditorStore } from "../../stores/agent";
import { yamlToAgent } from "../../utils/yaml";

export function QuickActions() {
  const navigate = useNavigate();
  const setConfig = useAgentEditorStore((s) => s.setConfig);
  const reset = useAgentEditorStore((s) => s.reset);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleCreateScratch() {
    reset();
    navigate("/wizard");
  }

  function handleImportClick() {
    fileInputRef.current?.click();
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const text = ev.target?.result as string;
        const config = yamlToAgent(text);
        setConfig(config);
        navigate("/wizard");
      } catch (err) {
        alert(
          "Failed to parse YAML: " +
            (err instanceof Error ? err.message : "Unknown error")
        );
      }
    };
    reader.readAsText(file);
    // Reset so the same file can be re-selected
    e.target.value = "";
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card hoverable onClick={handleCreateScratch}>
        <div className="text-center py-4">
          <div className="text-3xl mb-2">+</div>
          <h3 className="text-lg font-semibold text-gray-100">
            Create from Scratch
          </h3>
          <p className="text-sm text-gray-400 mt-1">
            Build a new agent step by step
          </p>
        </div>
      </Card>

      <Card hoverable onClick={() => navigate("/templates")}>
        <div className="text-center py-4">
          <div className="text-3xl mb-2">&#9776;</div>
          <h3 className="text-lg font-semibold text-gray-100">
            Start from Template
          </h3>
          <p className="text-sm text-gray-400 mt-1">
            Pick a pre-built agent template
          </p>
        </div>
      </Card>

      <Card hoverable onClick={handleImportClick}>
        <div className="text-center py-4">
          <div className="text-3xl mb-2">&#8593;</div>
          <h3 className="text-lg font-semibold text-gray-100">Import YAML</h3>
          <p className="text-sm text-gray-400 mt-1">
            Load an existing agent config file
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".yaml,.yml"
          className="hidden"
          onChange={handleFileChange}
        />
      </Card>
    </div>
  );
}
