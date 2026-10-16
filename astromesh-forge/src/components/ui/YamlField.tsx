import { useState } from "react";
import yaml from "js-yaml";

/**
 * Edit an arbitrary manifest section as YAML. Parsed on blur; invalid YAML is shown and
 * not applied. Empty text removes the section (onChange(undefined)).
 */
export function YamlField({
  label,
  id,
  value,
  onChange,
  hint,
}: {
  label: string;
  id: string;
  value: unknown;
  onChange: (v: unknown) => void;
  hint?: string;
}) {
  const dump = (v: unknown) => (v === undefined ? "" : yaml.dump(v, { lineWidth: 100 }));
  const [text, setText] = useState(() => dump(value));
  const [error, setError] = useState<string | null>(null);

  function commit() {
    try {
      const parsed = text.trim() ? yaml.load(text) : undefined;
      setError(null);
      onChange(parsed);
    } catch (e) {
      setError(e instanceof Error ? e.message.split("\n")[0] : "Invalid YAML");
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm text-gray-400">
        {label}
      </label>
      {hint && <p className="text-xs text-gray-500">{hint}</p>}
      <textarea
        id={id}
        className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 font-mono text-xs min-h-[80px] resize-y focus:outline-none focus:border-cyan-500"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        spellCheck={false}
      />
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
