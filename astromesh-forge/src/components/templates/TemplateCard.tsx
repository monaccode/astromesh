import type { TemplateSummary } from "../../types/template";
import { Card } from "../ui/Card";
import { Badge } from "../ui/Badge";

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

interface TemplateCardProps {
  template: TemplateSummary;
  onClick: () => void;
}

export function TemplateCard({ template, onClick }: TemplateCardProps) {
  return (
    <Card hoverable onClick={onClick}>
      <div className="flex flex-col gap-3">
        <div>
          <Badge variant="success">
            {CATEGORY_LABELS[template.category] || template.category}
          </Badge>
        </div>

        <h3 className="text-lg font-semibold text-gray-100">
          {template.display_name}
        </h3>

        <p className="text-sm text-gray-400 line-clamp-2">
          {template.description}
        </p>

        {template.recommended_channels.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {template.recommended_channels.map((ch) => (
              <Badge key={ch.channel} variant="default">
                {ch.channel}
              </Badge>
            ))}
          </div>
        )}

        {template.tags.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {template.tags.map((tag) => (
              <span
                key={tag}
                className="text-xs text-gray-500 bg-gray-800 border border-gray-700 rounded px-1.5 py-0.5"
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
