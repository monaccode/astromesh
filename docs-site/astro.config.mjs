import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://monaccode.github.io',
  base: '/astromesh',
  integrations: [
    starlight({
      title: 'Astromesh',
      logo: {
        src: './public/astromesh-logo.png',
        alt: 'Astromesh',
        replacesTitle: true,
      },
      description: 'AI Agent Runtime Platform',
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/monaccode/astromesh' },
      ],
      components: {
        // Dark-only: hide the toggle and force the dark theme on every load.
        ThemeSelect: './src/components/ThemeSelect.astro',
        ThemeProvider: './src/components/ThemeProvider.astro',
        SocialIcons: './src/components/SocialIcons.astro',
      },
      sidebar: [
        {
          label: 'Getting Started',
          items: [
            { label: 'What is Astromesh?', slug: 'getting-started/what-is-astromesh' },
            { label: 'The Ecosystem', slug: 'getting-started/ecosystem' },
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
            { label: 'Forge, API & on-disk agents', slug: 'configuration/forge-api-storage' },
            { label: 'Profiles Reference', slug: 'configuration/profiles' },
            { label: 'Multi-agent Composition', slug: 'configuration/multi-agent' },
            { label: 'Channels', slug: 'configuration/channels' },
          ],
        },
        {
          label: 'Deployment',
          items: [
            { label: 'Standalone (from source)', slug: 'deployment/standalone' },
            { label: 'Astromesh OS (appliance)', slug: 'deployment/astromesh-os' },
            { label: 'Astromesh Node (service)', link: '/astromesh/node/introduction/' },
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
        {
          label: 'Agent Development Kit',
          items: [
            { label: 'Introduction', slug: 'adk/introduction' },
            { label: 'Quick Start', slug: 'adk/quickstart' },
            { label: 'Defining Agents', slug: 'adk/defining-agents' },
            { label: 'Creating Tools', slug: 'adk/creating-tools' },
            { label: 'Multi-Agent Teams', slug: 'adk/multi-agent' },
            { label: 'Remote Execution', slug: 'adk/remote-execution' },
            { label: 'CLI Reference', slug: 'adk/cli-reference' },
          ],
        },
        {
          label: 'Forge (Web Builder)',
          items: [
            { label: 'Introduction', slug: 'forge/introduction' },
            { label: 'Quick Start', slug: 'forge/quickstart' },
            { label: 'Wizard Guide', slug: 'forge/wizard-guide' },
            { label: 'Canvas Guide', slug: 'forge/canvas-guide' },
            { label: 'Agent Templates', slug: 'forge/templates' },
            { label: 'Deployment', slug: 'forge/deployment' },
          ],
        },
        {
          label: 'Cortex (Desktop IDE)',
          items: [
            { label: 'Introduction', slug: 'cortex/introduction' },
            { label: 'Quick Start', slug: 'cortex/quickstart' },
            { label: 'Runtimes & Connections', slug: 'cortex/runtimes' },
            { label: 'Workspaces & Editor', slug: 'cortex/workspaces' },
          ],
        },
        {
          label: 'Astromesh Leia',
          items: [
            { label: 'Introduction', slug: 'leia/introduction' },
            { label: 'Quick Start', slug: 'leia/quickstart' },
            { label: 'Command Reference', slug: 'leia/commands' },
            { label: 'Templates & Agents', slug: 'leia/templates' },
          ],
        },
        {
          label: 'Astromesh Orbit',
          items: [
            { label: 'Introduction', slug: 'orbit/introduction' },
            { label: 'Quick Start', slug: 'orbit/quickstart' },
            { label: 'Configuration', slug: 'orbit/configuration' },
            { label: 'GCP Provider', slug: 'orbit/gcp-provider' },
            { label: 'CLI Reference', slug: 'orbit/cli-reference' },
          ],
        },
        {
          label: 'Astromesh Nexus',
          items: [
            { label: 'Introduction', slug: 'nexus/introduction' },
            { label: 'Architecture & CRDs', slug: 'nexus/architecture' },
            { label: 'Quick Start', slug: 'nexus/quickstart' },
            { label: 'API Reference', slug: 'nexus/api-reference' },
          ],
        },
        {
          label: 'Astromesh Node',
          items: [
            { label: 'Introduction', slug: 'node/introduction' },
            { label: 'Quick Start', slug: 'node/quick-start' },
            {
              label: 'Installation',
              items: [
                { label: 'Debian / Ubuntu', slug: 'node/installation/linux-debian' },
                { label: 'RHEL / Fedora', slug: 'node/installation/linux-redhat' },
                { label: 'macOS', slug: 'node/installation/macos' },
                { label: 'Windows', slug: 'node/installation/windows' },
              ],
            },
            { label: 'Configuration', slug: 'node/configuration' },
            { label: 'CLI Reference', slug: 'node/cli-reference' },
            { label: 'Troubleshooting', slug: 'node/troubleshooting' },
          ],
        },
        {
          label: 'Astromesh OS',
          items: [
            { label: 'Introduction', slug: 'os/introduction' },
            { label: 'Architecture', slug: 'os/architecture' },
            { label: 'Operations & Commands', slug: 'os/operations' },
            { label: 'Building the Image', slug: 'os/building' },
            { label: 'Phases & Roadmap', slug: 'os/roadmap' },
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
