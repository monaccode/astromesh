import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://monaccode.github.io',
  base: '/astromesh',
  integrations: [
    starlight({
      title: 'Astromesh',
      description: 'AI Agent Runtime Platform',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/monaccode/astromesh' },
      ],
      components: {
        ThemeSelect: './src/components/ThemeSelect.astro',
        SocialIcons: './src/components/SocialIcons.astro',
      },
      sidebar: [
        {
          label: 'Getting Started',
          items: [
            { label: 'What is Astromesh?', slug: 'getting-started/what-is-astromesh' },
            { label: 'Installation', slug: 'getting-started/installation' },
            { label: 'Quick Start', slug: 'getting-started/quickstart' },
            { label: 'Your First Agent', slug: 'getting-started/first-agent' },
            { label: 'Developer Tools', slug: 'getting-started/developer-tools' },
          ],
        },
        {
          label: 'Architecture',
          items: [
            { label: 'Overview', slug: 'architecture/overview' },
            { label: 'Four-Layer Design', slug: 'architecture/four-layer-design' },
            { label: 'Agent Execution Pipeline', slug: 'architecture/agent-pipeline' },
            { label: 'Kubernetes-Style Architecture', slug: 'architecture/k8s-architecture' },
          ],
        },
        {
          label: 'Configuration',
          items: [
            { label: 'Init Wizard', slug: 'configuration/init-wizard' },
            { label: 'Agent YAML Schema', slug: 'configuration/agent-yaml' },
            { label: 'Provider Configuration', slug: 'configuration/providers' },
            { label: 'Runtime Config', slug: 'configuration/runtime-config' },
            { label: 'Profiles Reference', slug: 'configuration/profiles' },
            { label: 'Multi-agent Composition', slug: 'configuration/multi-agent' },
            { label: 'Channels', slug: 'configuration/channels' },
          ],
        },
        {
          label: 'Deployment',
          items: [
            { label: 'Standalone (from source)', slug: 'deployment/standalone' },
            { label: 'Astromesh OS', slug: 'deployment/astromesh-os' },
            { label: 'Docker Single Node', slug: 'deployment/docker-single' },
            { label: 'Docker Maia', slug: 'deployment/docker-maia' },
            { label: 'Docker Maia + GPU', slug: 'deployment/docker-maia-gpu' },
            { label: 'Helm / Kubernetes', slug: 'deployment/helm-kubernetes' },
            { label: 'ArgoCD / GitOps', slug: 'deployment/argocd-gitops' },
          ],
        },
        {
          label: 'Advanced',
          items: [
            { label: 'Rust Native Extensions', slug: 'advanced/rust-extensions' },
            { label: 'WhatsApp Integration', slug: 'advanced/whatsapp' },
            { label: 'Observability Stack', slug: 'advanced/observability' },
            { label: 'Maia Protocol Internals', slug: 'advanced/maia-internals' },
          ],
        },
        {
          label: 'Reference',
          items: [
            { label: 'Runtime Engine', slug: 'reference/core/runtime-engine' },
            { label: 'Model Router', slug: 'reference/core/model-router' },
            { label: 'Tool Registry', slug: 'reference/core/tool-registry' },
            { label: 'Built-in Tools', slug: 'reference/core/builtin-tools' },
            { label: 'Memory Manager', slug: 'reference/core/memory-manager' },
            { label: 'Daemon (astromeshd)', slug: 'reference/os/daemon' },
            { label: 'CLI (astromeshctl)', slug: 'reference/os/cli' },
            { label: 'VS Code Extension', slug: 'reference/os/vscode-extension' },
            { label: 'Gossip Protocol', slug: 'reference/mesh/gossip-protocol' },
            { label: 'Scheduling & Routing', slug: 'reference/mesh/scheduling' },
            { label: 'Environment Variables', slug: 'reference/env-vars' },
            { label: 'API Endpoints', slug: 'reference/api-endpoints' },
            { label: 'CLI Commands', slug: 'reference/cli-commands' },
          ],
        },
      ],
      editLink: {
        baseUrl: 'https://github.com/monaccode/astromesh/edit/develop/docs-site/',
      },
      customCss: ['./src/styles/custom.css'],
    }),
  ],
});
