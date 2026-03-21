import { useState, useEffect, useMemo } from "react";
import { Search, BookTemplate } from "lucide-react";
import type { TemplateSummary } from "../../types/template";
import { useConnectionStore } from "../../stores/connection";
import { Skeleton } from "../ui/Skeleton";
import { EmptyState } from "../ui/EmptyState";
import { TemplateCard } from "./TemplateCard";
import { TemplatePreview } from "./TemplatePreview";

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

export function TemplateGallery() {
  const client = useConnectionStore((s) => s.client);

  const [templates, setTemplates] = useState<TemplateSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("all");
  const [previewName, setPreviewName] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    client
      .listTemplates()
      .then(setTemplates)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [client]);

  const categories = useMemo(() => {
    const unique = Array.from(new Set(templates.map((t) => t.category)));
    return unique.sort();
  }, [templates]);

  const filtered = useMemo(() => {
    let result = templates;

    if (activeCategory !== "all") {
      result = result.filter((t) => t.category === activeCategory);
    }

    if (search.trim()) {
      const q = search.toLowerCase();
      result = result.filter(
        (t) =>
          t.display_name.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q) ||
          t.tags.some((tag) => tag.toLowerCase().includes(q))
      );
    }

    return result;
  }, [templates, activeCategory, search]);

  return (
    <div className="p-6">
      <h1 className="text-2xl font-bold text-gray-100 mb-6">Templates</h1>

      {/* Search */}
      <div className="mb-4 max-w-md relative">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
        <input
          type="text"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg pl-9 pr-3 py-2 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-cyan-500"
          placeholder="Search templates..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {/* Category Tabs */}
      <div className="flex flex-wrap gap-2 mb-6">
        <button
          className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            activeCategory === "all"
              ? "bg-cyan-500 text-white"
              : "bg-gray-800 text-gray-400 hover:text-gray-200"
          }`}
          onClick={() => setActiveCategory("all")}
        >
          All
        </button>
        {categories.map((cat) => (
          <button
            key={cat}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeCategory === cat
                ? "bg-cyan-500 text-white"
                : "bg-gray-800 text-gray-400 hover:text-gray-200"
            }`}
            onClick={() => setActiveCategory(cat)}
          >
            {CATEGORY_LABELS[cat] || cat}
          </button>
        ))}
      </div>

      {/* Content */}
      {loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }, (_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      )}
      {error && <p className="text-red-400">Error: {error}</p>}

      {!loading && !error && filtered.length === 0 && (
        <EmptyState
          icon={BookTemplate}
          title="No templates found"
          description="Try adjusting your search or category filter"
        />
      )}

      {!loading && !error && filtered.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((t) => (
            <TemplateCard
              key={t.name}
              template={t}
              onClick={() => setPreviewName(t.name)}
            />
          ))}
        </div>
      )}

      {/* Preview Modal */}
      <TemplatePreview
        templateName={previewName}
        open={previewName !== null}
        onClose={() => setPreviewName(null)}
      />
    </div>
  );
}
