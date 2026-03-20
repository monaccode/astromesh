function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_]+/g, "-")
    .replace(/-+/g, "-");
}

const FILTERS: Record<string, (s: string) => string> = {
  slugify,
  lower: (s) => s.toLowerCase(),
  upper: (s) => s.toUpperCase(),
};

export function resolveTemplate(
  template: string,
  variables: Record<string, string>
): string {
  return template.replace(/\{\{(\w+)(?:\|(\w+))?\}\}/g, (match, key, filter) => {
    const value = variables[key];
    if (value === undefined) return match;
    if (filter && FILTERS[filter]) return FILTERS[filter](value);
    return value;
  });
}

export function resolveTemplateObject<T>(obj: T, variables: Record<string, string>): T {
  if (typeof obj === "string") return resolveTemplate(obj, variables) as T;
  if (Array.isArray(obj)) return obj.map((item) => resolveTemplateObject(item, variables)) as T;
  if (obj !== null && typeof obj === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(obj)) {
      result[key] = resolveTemplateObject(value, variables);
    }
    return result as T;
  }
  return obj;
}
