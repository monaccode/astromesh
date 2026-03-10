---
title: "ArgoCD / GitOps"
description: "Automated multi-environment deployment with ArgoCD"
---

This guide covers deploying Astromesh across multiple environments using ArgoCD and GitOps principles. Push configuration changes to Git, and ArgoCD automatically syncs them to your Kubernetes clusters.

## What and Why

GitOps is an operational model where the desired state of your infrastructure is stored in Git. Instead of running `helm install` or `kubectl apply` manually, you:

1. Commit configuration changes to a Git repository
2. ArgoCD detects the change
3. ArgoCD syncs the Kubernetes cluster to match the desired state
4. Rolling updates happen automatically

This provides:

- **Audit trail** -- every change is a Git commit with author, timestamp, and diff
- **Reproducibility** -- any environment can be recreated from the Git state
- **Rollback** -- revert a Git commit to roll back a deployment
- **Multi-environment consistency** -- dev, staging, and prod all deploy from the same chart with different values

## Prerequisites

| Requirement | Version | Check command |
|-------------|---------|---------------|
| Kubernetes | 1.26+ | `kubectl version` |
| ArgoCD | 2.8+ | `argocd version` |
| Helm | 3.12+ | `helm version` |
| Git repo | accessible from ArgoCD | -- |

### Verify ArgoCD is installed

```bash
kubectl get pods -n argocd
```

Expected output:

```
NAME                                               READY   STATUS    RESTARTS   AGE
argocd-application-controller-0                    1/1     Running   0          2d
argocd-applicationset-controller-7b74965f7-x2k4m   1/1     Running   0          2d
argocd-dex-server-6dcf645b6b-abc12                 1/1     Running   0          2d
argocd-notifications-controller-5c4d48f9b-def34    1/1     Running   0          2d
argocd-redis-6976fc7dfc-ghi56                      1/1     Running   0          2d
argocd-repo-server-7c4f568f7-jkl78                 1/1     Running   0          2d
argocd-server-7bc7684f8d-mno90                     1/1     Running   0          2d
```

If ArgoCD is not installed, install it:

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

### Verify ArgoCD can access the repository

ArgoCD needs read access to your Git repository. For private repos, add credentials:

```bash
argocd repo add https://github.com/monaccode/astromech-platform.git \
  --username git \
  --password ghp_your_token
```

Expected output:

```
Repository 'https://github.com/monaccode/astromech-platform.git' added
```

## Step-by-step Setup

### 1. Review the ApplicationSet

The Astromesh repository includes an ArgoCD ApplicationSet at `deploy/gitops/argocd/applicationset.yaml`:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: astromesh
  namespace: argocd
spec:
  generators:
    - list:
        elements:
          - env: dev
            namespace: astromesh-dev
            valuesFile: values-dev.yaml
          - env: staging
            namespace: astromesh-staging
            valuesFile: values-staging.yaml
          - env: prod
            namespace: astromesh-prod
            valuesFile: values-prod.yaml
  template:
    metadata:
      name: astromesh-{{env}}
    spec:
      project: default
      source:
        repoURL: https://github.com/monaccode/astromech-platform.git
        targetRevision: HEAD
        path: deploy/helm/astromesh
        helm:
          valueFiles:
            - "{{valuesFile}}"
      destination:
        server: https://kubernetes.default.svc
        namespace: "{{namespace}}"
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
```

This creates one ArgoCD Application per environment, each deploying the same Helm chart with different values files.

### 2. Deploy the ApplicationSet

```bash
kubectl apply -f deploy/gitops/argocd/applicationset.yaml
```

Expected output:

```
applicationset.argoproj.io/astromesh created
```

### 3. Verify the Applications

```bash
argocd app list
```

Expected output:

```
NAME              CLUSTER                         NAMESPACE          PROJECT  STATUS  HEALTH   SYNCPOLICY  CONDITIONS
astromesh-dev     https://kubernetes.default.svc  astromesh-dev      default  Synced  Healthy  Auto-Prune  <none>
astromesh-staging https://kubernetes.default.svc  astromesh-staging  default  Synced  Healthy  Auto-Prune  <none>
astromesh-prod    https://kubernetes.default.svc  astromesh-prod     default  Synced  Healthy  Auto-Prune  <none>
```

All three environments show `Synced` and `Healthy`.

### 4. Check pods in each namespace

```bash
kubectl get pods -n astromesh-dev
```

Expected output:

```
NAME                                    READY   STATUS    RESTARTS   AGE
astromesh-5d8f9c7b6-x2k4m              1/1     Running   0          2m
astromesh-postgresql-0                  1/1     Running   0          2m
astromesh-redis-master-0                1/1     Running   0          2m
```

```bash
kubectl get pods -n astromesh-prod
```

Expected output:

```
NAME                                    READY   STATUS    RESTARTS   AGE
astromesh-5d8f9c7b6-a1b2c              1/1     Running   0          2m
astromesh-5d8f9c7b6-d3e4f              1/1     Running   0          2m
astromesh-5d8f9c7b6-g5h6i              1/1     Running   0          2m
astromesh-vllm-7f8g9h0i-j1k2l          1/1     Running   0          2m
astromesh-tei-embeddings-m3n4o-p5q6r   1/1     Running   0          2m
astromesh-tei-reranker-s7t8u-v9w0x     1/1     Running   0          2m
```

Production has 3 Astromesh replicas, vLLM, and two TEI instances as defined in `values-prod.yaml`.

## Configuration

### Environments

The ApplicationSet uses a list generator to create one Application per environment:

| Environment | Namespace | Values File | Auto-sync | Description |
|-------------|-----------|-------------|-----------|-------------|
| dev | `astromesh-dev` | `values-dev.yaml` | Yes | Development with all subcharts, no GPU limits |
| staging | `astromesh-staging` | `values-staging.yaml` | Yes | Pre-production validation |
| prod | `astromesh-prod` | `values-prod.yaml` | Yes | Production with external DBs, GPU, TLS |

### Sync Policy

```yaml
syncPolicy:
  automated:
    prune: true       # Delete resources removed from Git
    selfHeal: true    # Revert manual cluster changes to match Git
  syncOptions:
    - CreateNamespace=true  # Create namespace if it doesn't exist
```

- **`prune: true`** -- if you remove a resource from your Helm chart, ArgoCD deletes it from the cluster
- **`selfHeal: true`** -- if someone manually edits a resource in the cluster, ArgoCD reverts it to match Git

## Workflow

The GitOps workflow for making changes:

### 1. Edit configuration in Git

For example, to scale production to 5 replicas, edit `deploy/helm/astromesh/values-prod.yaml`:

```yaml
replicaCount: 5
```

### 2. Commit and push

```bash
git add deploy/helm/astromesh/values-prod.yaml
git commit -m "feat: scale production to 5 replicas"
git push origin main
```

### 3. ArgoCD detects the change

ArgoCD polls the repository (default every 3 minutes) or receives a webhook notification. It detects the diff between the desired state (Git) and the live state (cluster).

### 4. ArgoCD syncs

Because `automated.selfHeal: true` is set, ArgoCD automatically syncs:

```bash
argocd app get astromesh-prod
```

Expected output:

```
Name:               astromesh-prod
Server:             https://kubernetes.default.svc
Namespace:          astromesh-prod
Repo:               https://github.com/monaccode/astromech-platform.git
Path:               deploy/helm/astromesh
Target:             HEAD
Status:             Synced
Health:             Progressing
```

### 5. Rolling update completes

```bash
kubectl get pods -n astromesh-prod
```

Expected output:

```
NAME                                    READY   STATUS    RESTARTS   AGE
astromesh-5d8f9c7b6-a1b2c              1/1     Running   0          10m
astromesh-5d8f9c7b6-d3e4f              1/1     Running   0          10m
astromesh-5d8f9c7b6-g5h6i              1/1     Running   0          10m
astromesh-5d8f9c7b6-j7k8l              1/1     Running   0          30s
astromesh-5d8f9c7b6-m9n0o              1/1     Running   0          30s
```

Five replicas running.

## Customizing the ApplicationSet

### Change repository URL

Edit `deploy/gitops/argocd/applicationset.yaml`:

```yaml
source:
  repoURL: https://github.com/your-org/your-repo.git
```

### Change target branch

To deploy from a specific branch instead of HEAD:

```yaml
source:
  targetRevision: main
```

Or use a tag:

```yaml
source:
  targetRevision: v0.10.0
```

### Deploy to a different cluster

```yaml
destination:
  server: https://remote-cluster-api.example.com
  namespace: "{{namespace}}"
```

### Disable auto-sync for production

For manual approval before production deployments:

```yaml
generators:
  - list:
      elements:
        - env: dev
          namespace: astromesh-dev
          valuesFile: values-dev.yaml
        - env: staging
          namespace: astromesh-staging
          valuesFile: values-staging.yaml
        - env: prod
          namespace: astromesh-prod
          valuesFile: values-prod.yaml
```

Then override sync policy per-environment by creating separate ApplicationSets or using a matrix generator with sync policy conditions. For simpler control, disable auto-sync on prod after creation:

```bash
argocd app set astromesh-prod --sync-policy none
```

## Adding New Environments

To add a new environment (e.g., `qa`):

### 1. Create a values file

```bash
cp deploy/helm/astromesh/values-staging.yaml deploy/helm/astromesh/values-qa.yaml
```

Edit `values-qa.yaml` with QA-specific settings.

### 2. Add to the ApplicationSet

Edit `deploy/gitops/argocd/applicationset.yaml`, add to the `elements` list:

```yaml
generators:
  - list:
      elements:
        - env: dev
          namespace: astromesh-dev
          valuesFile: values-dev.yaml
        - env: qa
          namespace: astromesh-qa
          valuesFile: values-qa.yaml
        - env: staging
          namespace: astromesh-staging
          valuesFile: values-staging.yaml
        - env: prod
          namespace: astromesh-prod
          valuesFile: values-prod.yaml
```

### 3. Commit and apply

```bash
git add deploy/
git commit -m "feat: add QA environment"
git push origin main
kubectl apply -f deploy/gitops/argocd/applicationset.yaml
```

ArgoCD creates the new `astromesh-qa` Application and syncs it.

## Promotion Workflow

Promote changes from dev to staging to production:

### 1. Make changes in dev values

Edit `deploy/helm/astromesh/values-dev.yaml`:

```yaml
config:
  agents:
    new-agent.agent.yaml: |
      apiVersion: astromesh/v1
      kind: Agent
      metadata:
        name: new-agent
      spec:
        identity:
          display_name: "New Agent"
        model:
          primary:
            provider: ollama
            model: llama3.1:8b
        orchestration:
          pattern: react
```

Commit, push, and verify in dev.

### 2. Promote to staging

Copy the agent definition to `values-staging.yaml`:

```bash
# Copy the new agent config section
git diff values-dev.yaml  # Review what was added
# Apply the same change to values-staging.yaml
```

Commit and push. ArgoCD syncs staging.

### 3. Promote to production

After validating in staging, apply the same change to `values-prod.yaml`. Commit and push.

Each promotion is a Git commit, providing a clear audit trail of what changed and when.

## Rollback

### Using ArgoCD

Roll back to a previous sync:

```bash
argocd app history astromesh-prod
```

Expected output:

```
ID  DATE                           REVISION
2   2026-03-09 11:30:00 +0000 UTC  abc1234
1   2026-03-09 10:00:00 +0000 UTC  def5678
```

```bash
argocd app rollback astromesh-prod 1
```

Expected output:

```
TIMESTAMP                  GROUP/KIND      NAMESPACE        NAME          STATUS    HEALTH
2026-03-09T10:00:00+00:00  apps/Deployment astromesh-prod   astromesh     Synced    Healthy
```

### Using Git

Revert the commit that introduced the problem:

```bash
git revert abc1234
git push origin main
```

ArgoCD detects the revert and syncs the cluster back to the previous state.

## Common Operations

### View sync status

```bash
# All environments
argocd app list

# Specific environment
argocd app get astromesh-prod
```

### Manual sync

If auto-sync is disabled or you want to trigger immediately:

```bash
argocd app sync astromesh-prod
```

Expected output:

```
TIMESTAMP                  GROUP/KIND      NAMESPACE        NAME          STATUS    HEALTH
2026-03-09T11:00:00+00:00  /Service        astromesh-prod   astromesh     Synced    Healthy
2026-03-09T11:00:00+00:00  apps/Deployment astromesh-prod   astromesh     Synced    Healthy

Message:  successfully synced (all tasks run)
```

### View diff before sync

```bash
argocd app diff astromesh-prod
```

### Access ArgoCD UI

```bash
kubectl port-forward svc/argocd-server 8080:443 -n argocd
```

Open `https://localhost:8080`. Get the initial admin password:

```bash
argocd admin initial-password -n argocd
```

## Troubleshooting

### Sync failed

```bash
argocd app get astromesh-prod
```

If status shows `OutOfSync` or `SyncFailed`:

```bash
argocd app sync astromesh-prod --retry-limit 3
```

Check the sync details:

```bash
argocd app get astromesh-prod --show-operation
```

Common causes:

- **Helm template error:** invalid YAML in values file. Test locally:

```bash
helm template astromesh ./deploy/helm/astromesh -f deploy/helm/astromesh/values-prod.yaml
```

- **Resource conflict:** another controller manages the same resource. Check annotations.

- **Dependency not downloaded:** Helm chart dependencies need to be in the `charts/` directory or resolvable by ArgoCD.

### Secret issues

ArgoCD stores manifests in Git, which means secrets should not be committed in plain text. Use one of these approaches:

1. **External Secrets Operator** -- secrets synced from AWS/GCP/Vault (see [Helm guide](/astromech-platform/deployment/helm-kubernetes/#external-secrets-eso))
2. **Sealed Secrets** -- encrypted in Git, decrypted in cluster
3. **existingSecret** -- create secrets out-of-band, reference by name in values

Do not put API keys or passwords in values files that are committed to Git.

### Configuration drift

If someone manually changes a resource in the cluster, ArgoCD detects drift and shows `OutOfSync`. With `selfHeal: true`, it automatically reverts the change.

To check for drift:

```bash
argocd app diff astromesh-prod
```

### ArgoCD cannot reach the repository

```
rpc error: code = Unknown desc = authentication required
```

Add or update repository credentials:

```bash
argocd repo add https://github.com/monaccode/astromech-platform.git \
  --username git \
  --password ghp_new_token
```

### Application stuck in "Progressing"

Check pod status:

```bash
kubectl get pods -n astromesh-prod
kubectl describe pod <pod-name> -n astromesh-prod
```

Common causes:

- Image pull errors (wrong tag or registry auth)
- Insufficient resources (CPU/memory limits too low)
- Failed health checks (readiness probe failing)

### Webhook setup (faster sync)

By default, ArgoCD polls every 3 minutes. For faster sync, configure a GitHub webhook:

1. In the ArgoCD UI, go to Settings > Repositories
2. Note the webhook URL: `https://argocd.example.com/api/webhook`
3. In GitHub, go to your repo Settings > Webhooks > Add webhook
4. Set the Payload URL to the ArgoCD webhook endpoint
5. Set Content type to `application/json`
6. Select "Just the push event"

Now ArgoCD syncs within seconds of a push.
