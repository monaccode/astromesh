import type { AgentConfig } from "./agent";

export interface TemplateVariable {
  key: string;
  label: string;
  placeholder?: string;
  default?: string;
  required: boolean;
}

export interface TemplateChannel {
  channel: string;
  reason: string;
}

export interface TemplateSummary {
  name: string;
  version: string;
  category: string;
  tags: string[];
  display_name: string;
  description: string;
  recommended_channels: TemplateChannel[];
}

export interface TemplateDetail extends TemplateSummary {
  variables: TemplateVariable[];
  agent_config: AgentConfig;
}
