import { useState } from "react";
import { Input } from "../ui/Input";
import { Select } from "../ui/Select";
import type { GuardrailConfig } from "../../types/agent";
import {
  GUARDRAIL_SPECS,
  defaultGuardrail,
  guardrailTypesFor,
  isGuardrailType,
  type GuardrailSide,
} from "../../utils/guardrails";

function ListField({
  label,
  id,
  value,
  onChange,
}: {
  label: string;
  id: string;
  value: string[] | undefined;
  onChange: (v: string[]) => void;
}) {
  // Local text so a trailing newline survives typing; the rule only gets the non-empty lines.
  const [text, setText] = useState((value ?? []).join("\n"));
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-sm text-gray-400">
        {label} (one per line)
      </label>
      <textarea
        id={id}
        className="bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm text-gray-100 min-h-[60px]"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChange(e.target.value.split("\n").map((l) => l.trim()).filter(Boolean));
        }}
      />
    </div>
  );
}

/** Edits one guardrail rule: only the types valid for `side`, their actions and type fields. */
export function GuardrailRuleFields({
  idPrefix,
  side,
  rule,
  onChange,
}: {
  idPrefix: string;
  side: GuardrailSide;
  rule: GuardrailConfig;
  onChange: (r: GuardrailConfig) => void;
}) {
  const known = isGuardrailType(rule.type);
  const typeOptions: { value: string; label: string }[] = guardrailTypesFor(side).map((t) => ({
    value: t,
    label: GUARDRAIL_SPECS[t].label,
  }));
  // A manifest may carry a type core ignores; keep it visible instead of silently rewriting it.
  if (!known || !typeOptions.some((o) => o.value === rule.type)) {
    typeOptions.unshift({ value: rule.type, label: `${rule.type} (unsupported here)` });
  }
  const actions = known ? GUARDRAIL_SPECS[rule.type as keyof typeof GUARDRAIL_SPECS].actions : [];
  const set = (u: Partial<GuardrailConfig>) => onChange({ ...rule, ...u });

  return (
    <div className="space-y-2">
      <Select
        label="Type"
        id={`${idPrefix}-type`}
        options={typeOptions}
        value={rule.type}
        onChange={(e) => {
          const t = e.target.value;
          if (!isGuardrailType(t)) return;
          const next = defaultGuardrail(t);
          onChange(rule.message ? { ...next, message: rule.message } : next);
        }}
      />
      {actions.length > 1 && (
        <Select
          label="Action"
          id={`${idPrefix}-action`}
          options={actions.map((a) => ({ value: a, label: a[0].toUpperCase() + a.slice(1) }))}
          value={rule.action ?? actions[0]}
          onChange={(e) => set({ action: e.target.value as GuardrailConfig["action"] })}
        />
      )}
      {rule.type === "topic_filter" && (
        <ListField
          label="Blocked topics"
          id={`${idPrefix}-topics`}
          value={rule.blocked_topics}
          onChange={(v) => set({ blocked_topics: v })}
        />
      )}
      {rule.type === "max_length" && (
        <Input
          label="Max characters"
          id={`${idPrefix}-chars`}
          type="number"
          min={1}
          value={String(rule.max_chars ?? "")}
          onChange={(e) => set({ max_chars: Number(e.target.value) || undefined })}
        />
      )}
      {rule.type === "content_filter" && (
        <>
          <ListField
            label="Blocked patterns (regex)"
            id={`${idPrefix}-patterns`}
            value={rule.blocked_patterns}
            onChange={(v) => set({ blocked_patterns: v })}
          />
          <ListField
            label="Forbidden keywords"
            id={`${idPrefix}-keywords`}
            value={rule.forbidden_keywords}
            onChange={(v) => set({ forbidden_keywords: v })}
          />
        </>
      )}
      {rule.type === "cost_limit" && (
        <>
          <Input
            label="Max output tokens per run"
            id={`${idPrefix}-tokens`}
            type="number"
            min={1}
            value={String(rule.max_tokens_per_turn ?? "")}
            onChange={(e) => set({ max_tokens_per_turn: Number(e.target.value) || undefined })}
          />
          <Select
            label="Count"
            id={`${idPrefix}-count`}
            options={[
              { value: "output", label: "Output tokens" },
              { value: "total", label: "Input + output" },
            ]}
            value={rule.count ?? "output"}
            onChange={(e) => set({ count: e.target.value as "output" | "total" })}
          />
        </>
      )}
      <Input
        label="Message (optional)"
        id={`${idPrefix}-message`}
        value={rule.message ?? ""}
        onChange={(e) => set({ message: e.target.value || undefined })}
      />
    </div>
  );
}
