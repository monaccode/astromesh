import type { ToolConfig } from "../types/agent";

/**
 * Client-side mirror of `astromesh/integrations/a2a.py` (build_a2a_tool, _policy, _auth) and
 * `astromesh_a2a.Policy.check_card_url`. Same limits, so Forge never emits a `type: a2a` tool
 * that would make core refuse to bootstrap the agent.
 */
export const A2A_MAX_BYTES = 16 * 1024 * 1024; // MAX_BYTES_TOPE, 16 MiB
export const A2A_MAX_TIMEOUT = 600; // TIMEOUT_TOPE, seconds
export const A2A_PARTS = ["text", "data", "file"] as const;
export type A2APart = (typeof A2A_PARTS)[number];
const ENV_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

export type A2AAuthKind = "none" | "api_key_env" | "bearer_env";

/** Form state; numbers stay strings so an empty field means "key absent, runtime default". */
export interface A2AForm {
  card_url: string;
  authKind: A2AAuthKind;
  authEnv: string;
  max_bytes: string;
  timeout: string;
  /** Empty = no `accept_parts` key (runtime default: text, data). */
  accept_parts: A2APart[];
  allow_insecure_http: boolean;
}

export type A2AErrors = Partial<Record<"name" | "card_url" | "authEnv" | "max_bytes" | "timeout", string>>;

export function a2aFormFrom(c: ToolConfig): A2AForm {
  const auth = c.auth ?? {};
  const authKind: A2AAuthKind =
    "api_key_env" in auth ? "api_key_env" : "bearer_env" in auth ? "bearer_env" : "none";
  const p = c.policy ?? {};
  return {
    card_url: typeof c.card_url === "string" ? c.card_url : "",
    authKind,
    authEnv: authKind === "none" ? "" : String(auth[authKind] ?? ""),
    max_bytes: p.max_bytes !== undefined ? String(p.max_bytes) : "",
    timeout: p.timeout !== undefined ? String(p.timeout) : "",
    accept_parts: A2A_PARTS.filter((x) => p.accept_parts?.includes(x)),
    allow_insecure_http: p.allow_insecure_http === true,
  };
}

/** Python `urlsplit` netloc: what sits between `scheme://` and the first `/`, `?` or `#`. */
function splitUrl(url: string): { scheme: string; netloc: string } {
  const m = /^([A-Za-z][A-Za-z0-9+.-]*):(.*)$/.exec(url);
  const scheme = m ? m[1].toLowerCase() : "";
  const rest = m ? m[2] : url;
  const netloc = rest.startsWith("//") ? rest.slice(2).split(/[/?#]/, 1)[0] : "";
  return { scheme, netloc };
}

function hostOf(netloc: string): string {
  const hostport = netloc.slice(netloc.lastIndexOf("@") + 1);
  if (hostport.startsWith("[")) return hostport.slice(1).split("]", 1)[0];
  return hostport.split(":", 1)[0];
}

export function validateA2A(name: string, f: A2AForm): A2AErrors {
  const e: A2AErrors = {};
  if (!name.trim()) e.name = "Required.";

  const url = f.card_url;
  if (!url) {
    e.card_url = "Required.";
  } else if ([...url].some((ch) => /\s/.test(ch) || ch.charCodeAt(0) < 32 || ch.charCodeAt(0) === 127)) {
    e.card_url = "Must not contain spaces or control characters.";
  } else {
    const { scheme, netloc } = splitUrl(url);
    if (!hostOf(netloc)) e.card_url = "Must be an absolute URL with a host.";
    else if (netloc.includes("@"))
      e.card_url = "Credentials in the URL are refused; use the auth environment variable.";
    else if (scheme !== "https" && !(scheme === "http" && f.allow_insecure_http))
      e.card_url = "Must be https (http only with “Allow insecure http”).";
  }

  if (f.authKind !== "none" && !ENV_NAME.test(f.authEnv))
    e.authEnv = "Environment variable name: letters, digits and _, not starting with a digit.";

  if (f.max_bytes !== "") {
    const v = Number(f.max_bytes);
    if (!Number.isInteger(v) || v < 1 || v > A2A_MAX_BYTES)
      e.max_bytes = `Integer between 1 and ${A2A_MAX_BYTES} (16 MiB).`;
  }
  if (f.timeout !== "") {
    const v = Number(f.timeout);
    if (!Number.isFinite(v) || v <= 0 || v > A2A_MAX_TIMEOUT)
      e.timeout = `Number > 0 and ≤ ${A2A_MAX_TIMEOUT} seconds.`;
  }
  return e;
}

/**
 * Write the a2a keys over `tool`. Empty fields drop their key (runtime default); keys the form
 * does not show (`rate_limit`, …) survive. Only call with a form that passed `validateA2A`.
 */
export function applyA2AForm(tool: ToolConfig, f: A2AForm): ToolConfig {
  const next: ToolConfig = { ...tool, card_url: f.card_url };

  if (f.authKind === "none") delete next.auth;
  else next.auth = { [f.authKind]: f.authEnv };

  const policy: NonNullable<ToolConfig["policy"]> = { ...tool.policy };
  if (f.max_bytes !== "") policy.max_bytes = Number(f.max_bytes);
  else delete policy.max_bytes;
  if (f.timeout !== "") policy.timeout = Number(f.timeout);
  else delete policy.timeout;
  if (f.accept_parts.length) policy.accept_parts = [...f.accept_parts];
  else delete policy.accept_parts;
  // An explicit `false` already in the YAML is kept; a new one is not written.
  if (f.allow_insecure_http || tool.policy?.allow_insecure_http !== undefined)
    policy.allow_insecure_http = f.allow_insecure_http;
  else delete policy.allow_insecure_http;

  if (Object.keys(policy).length) next.policy = policy;
  else delete next.policy;
  return next;
}
