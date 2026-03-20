import yaml from "js-yaml";
import type { AgentConfig } from "../types/agent";

export function agentToYaml(config: AgentConfig): string {
  return yaml.dump(config, { lineWidth: 100, noRefs: true });
}

export function yamlToAgent(yamlStr: string): AgentConfig {
  return yaml.load(yamlStr) as AgentConfig;
}
