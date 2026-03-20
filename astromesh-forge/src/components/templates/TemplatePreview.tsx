import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import type { TemplateDetail } from "../../types/template";
import { useConnectionStore } from "../../stores/connection";
import { useAgentEditorStore } from "../../stores/agent";
import { resolveTemplateObject } from "../../utils/template-engine";
import { agentToYaml } from "../../utils/yaml";
import { Modal } from "../ui/Modal";
import { Input } from "../ui/Input";
import { Badge } from "../ui/Badge";
import { Button } from "../ui/Button";

const CATEGORY_LABELS: Record<string, string> = {
  sales: "Sales",
  customer_service: "Customer Service",
  collections: "Collections",
  marketing: "Marketing",
  food_and_beverage: "Food & Beverage",
  automotive: "Automotive",
  real_estate: "Real Estate",
  education: "Education",
  internal_ops: "Internal Ops",
};

interface TemplatePreviewProps {
  templateName: string | null;
  open: boolean;
  onClose: () => void;
}

export function TemplatePreview({ templateName, open, onClose }: TemplatePreviewProps) {
  const navigate = useNavigate();
  const client = useConnectionStore((s) => s.client);
  const loadFromTemplate = useAgentEditorStore((s) => s.loadFromTemplate);

  const [template, setTemplate] = useState<TemplateDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [variableValues, setVariableValues] = useState<Record<string, string>>({});

  useEffect(() => {
    if (!templateName || !open) return;

    setLoading(true);
    setError(null);
    setTemplate(null);

    client
      .getTemplate(templateName)
      .then((detail) => {
        setTemplate(detail);
        const defaults: Record<string, string> = {};
        for (const v of detail.variables) {
          if (v.default) defaults[v.key] = v.default;
        }
        setVariableValues(defaults);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [templateName, open, client]);

  function handleVariableChange(key: string, value: string) {
    setVariableValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleUseTemplate() {
    if (!template) return;
    const resolved = resolveTemplateObject(template.agent_config, variableValues);
    loadFromTemplate(resolved, template.name);
    onClose();
    navigate("/wizard");
  }

  const resolvedConfig = template
    ? resolveTemplateObject(template.agent_config, variableValues)
    : null;

  return (
    <Modal open={open} onClose={onClose} title={template?.display_name || "Template Preview"}>
      {loading && <p className="text-gray-400">Loading template...</p>}
      {error && <p className="text-red-400">Error: {error}</p>}

      {template && (
        <div className="flex flex-col gap-6">
          {/* Header */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <Badge variant="success">
                {CATEGORY_LABELS[template.category] || template.category}
              </Badge>
            </div>
            <p className="text-sm text-gray-400">{template.description}</p>
          </div>

          {/* Recommended Channels */}
          {template.recommended_channels.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-gray-300 mb-2">Recommended Channels</h4>
              <div className="flex flex-col gap-2">
                {template.recommended_channels.map((ch) => (
                  <div key={ch.channel} className="flex items-start gap-2">
                    <Badge variant="default">{ch.channel}</Badge>
                    <span className="text-xs text-gray-500">{ch.reason}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Variables Form */}
          {template.variables.length > 0 && (
            <div>
              <h4 className="text-sm font-medium text-gray-300 mb-2">Configuration</h4>
              <div className="flex flex-col gap-3">
                {template.variables.map((v) => (
                  <Input
                    key={v.key}
                    id={`var-${v.key}`}
                    label={`${v.label}${v.required ? " *" : ""}`}
                    placeholder={v.placeholder}
                    value={variableValues[v.key] || ""}
                    onChange={(e) => handleVariableChange(v.key, e.target.value)}
                  />
                ))}
              </div>
            </div>
          )}

          {/* YAML Preview */}
          {resolvedConfig && (
            <div>
              <h4 className="text-sm font-medium text-gray-300 mb-2">YAML Preview</h4>
              <pre className="bg-gray-950 border border-gray-700 rounded-lg p-3 text-xs text-gray-300 font-mono overflow-x-auto max-h-60 overflow-y-auto">
                {agentToYaml(resolvedConfig)}
              </pre>
            </div>
          )}

          {/* Actions */}
          <div className="flex justify-end gap-3">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button onClick={handleUseTemplate}>Use Template</Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
