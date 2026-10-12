import yaml from "js-yaml";
import type { AgentConfig } from "../types/agent";
import { cleanKnowledge } from "./knowledge";

export function agentToYaml(config: AgentConfig): string {
  const { knowledge, ...spec } = config.spec;
  const k = knowledge && cleanKnowledge(knowledge);
  config = { ...config, spec: k ? { ...spec, knowledge: k } : spec };
  return yaml.dump(config, { lineWidth: 100, noRefs: true });
}

export function yamlToAgent(yamlStr: string): AgentConfig {
  return yaml.load(yamlStr) as AgentConfig;
}
