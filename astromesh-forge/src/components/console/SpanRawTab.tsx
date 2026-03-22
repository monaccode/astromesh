import { useState } from "react";
import { Copy, Check } from "lucide-react";
import type { SpanTreeNode } from "../../utils/trace-tree";

export function SpanRawTab({ node }: { node: SpanTreeNode }) {
  const [copied, setCopied] = useState(false);

  const raw = JSON.stringify(
    { attributes: node.attributes, events: node.events },
    null,
    2,
  );

  const handleCopy = async () => {
    await navigator.clipboard.writeText(raw);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="p-3">
      <div className="flex justify-end mb-1">
        <button
          className="flex items-center gap-1 text-gray-400 hover:text-gray-200 text-[10px]"
          onClick={handleCopy}
        >
          {copied ? <Check size={10} /> : <Copy size={10} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      <pre className="text-gray-400 bg-gray-800 rounded p-3 text-[9px] overflow-x-auto overflow-y-auto max-h-[400px] whitespace-pre-wrap">
        {raw}
      </pre>
    </div>
  );
}
