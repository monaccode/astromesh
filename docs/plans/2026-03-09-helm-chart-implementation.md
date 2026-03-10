# Astromesh Helm Chart Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a production-ready Helm chart that deploys Astromesh on Kubernetes with PostgreSQL, Redis as hybrid dependencies and optional Ollama.

**Architecture:** Helm chart at `deploy/helm/astromesh/` using Bitnami subcharts for Postgres/Redis (disableable for external services). Astromesh config YAML files are mounted via ConfigMaps. Secrets support both inline values and existing secret references.

**Tech Stack:** Helm 3, Kubernetes 1.26+, Bitnami PostgreSQL/Redis charts, Ollama Helm chart

---

### Task 1: Chart Scaffold — Chart.yaml and _helpers.tpl

**Files:**
- Create: `deploy/helm/astromesh/Chart.yaml`
- Create: `deploy/helm/astromesh/templates/_helpers.tpl`
- Create: `deploy/helm/astromesh/.helmignore`

**Step 1: Create Chart.yaml with dependencies**

```yaml
apiVersion: v2
name: astromesh
description: Astromesh Agent Runtime Platform — deploy AI agents on Kubernetes
type: application
version: 0.1.0
appVersion: "0.4.0"
keywords:
  - ai
  - agents
  - llm
  - runtime
home: https://github.com/monaccode/astromesh
maintainers:
  - name: monaccode

dependencies:
  - name: postgresql
    version: "16.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: postgresql.enabled
  - name: redis
    version: "20.x.x"
    repository: https://charts.bitnami.com/bitnami
    condition: redis.enabled
  - name: ollama
    version: "1.x.x"
    repository: https://otwld.github.io/ollama-helm
    condition: ollama.enabled
```

**Step 2: Create _helpers.tpl**

Standard Helm helpers: `astromesh.name`, `astromesh.fullname`, `astromesh.chart`, `astromesh.labels`, `astromesh.selectorLabels`, `astromesh.serviceAccountName`.

```gotemplate
{{/*
Expand the name of the chart.
*/}}
{{- define "astromesh.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "astromesh.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "astromesh.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "astromesh.labels" -}}
helm.sh/chart: {{ include "astromesh.chart" . }}
{{ include "astromesh.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "astromesh.selectorLabels" -}}
app.kubernetes.io/name: {{ include "astromesh.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "astromesh.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "astromesh.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
PostgreSQL host — subchart or external
*/}}
{{- define "astromesh.postgresql.host" -}}
{{- if .Values.postgresql.enabled }}
{{- printf "%s-postgresql" (include "astromesh.fullname" .) }}
{{- else }}
{{- .Values.externalDatabase.host }}
{{- end }}
{{- end }}

{{/*
PostgreSQL port
*/}}
{{- define "astromesh.postgresql.port" -}}
{{- if .Values.postgresql.enabled }}
{{- "5432" }}
{{- else }}
{{- .Values.externalDatabase.port | default "5432" | toString }}
{{- end }}
{{- end }}

{{/*
Redis host — subchart or external
*/}}
{{- define "astromesh.redis.host" -}}
{{- if .Values.redis.enabled }}
{{- printf "%s-redis-master" (include "astromesh.fullname" .) }}
{{- else }}
{{- .Values.externalRedis.host }}
{{- end }}
{{- end }}

{{/*
Redis port
*/}}
{{- define "astromesh.redis.port" -}}
{{- if .Values.redis.enabled }}
{{- "6379" }}
{{- else }}
{{- .Values.externalRedis.port | default "6379" | toString }}
{{- end }}
{{- end }}
```

**Step 3: Create .helmignore**

```
.DS_Store
.git
.gitignore
.bzr
.bzrignore
.hg
.hgignore
.svn
*.swp
*.bak
*.tmp
*.orig
*~
.project
.idea
*.tmproj
.vscode
```

**Step 4: Commit**

```bash
git add deploy/helm/astromesh/Chart.yaml deploy/helm/astromesh/templates/_helpers.tpl deploy/helm/astromesh/.helmignore
git commit -m "feat(helm): scaffold chart with Chart.yaml, helpers, and helmignore"
```

---

### Task 2: values.yaml — Complete Default Configuration

**Files:**
- Create: `deploy/helm/astromesh/values.yaml`

**Step 1: Write values.yaml**

```yaml
# -- Number of Astromesh API replicas
replicaCount: 1

image:
  # -- Container image repository
  repository: astromesh
  # -- Image pull policy
  pullPolicy: IfNotPresent
  # -- Image tag (defaults to Chart appVersion)
  tag: ""

# -- Image pull secrets for private registries
imagePullSecrets: []
# -- Override chart name
nameOverride: ""
# -- Override fully qualified app name
fullnameOverride: ""

serviceAccount:
  # -- Create a ServiceAccount
  create: true
  # -- Annotations for the ServiceAccount
  annotations: {}
  # -- ServiceAccount name (generated if not set)
  name: ""

# -- Pod annotations
podAnnotations: {}
# -- Pod security context
podSecurityContext: {}
# -- Container security context
securityContext: {}

service:
  # -- Service type
  type: ClusterIP
  # -- Service port
  port: 8000

ingress:
  # -- Enable Ingress
  enabled: false
  # -- Ingress class name
  className: ""
  # -- Ingress annotations
  annotations: {}
  # -- Ingress hosts
  hosts:
    - host: astromesh.local
      paths:
        - path: /
          pathType: Prefix
  # -- Ingress TLS configuration
  tls: []

# -- Resource requests and limits
resources: {}
  # requests:
  #   cpu: 250m
  #   memory: 512Mi
  # limits:
  #   cpu: "1"
  #   memory: 1Gi

autoscaling:
  # -- Enable HPA
  enabled: false
  # -- Minimum replicas
  minReplicas: 1
  # -- Maximum replicas
  maxReplicas: 5
  # -- Target CPU utilization percentage
  targetCPUUtilizationPercentage: 80

# -- Node selector
nodeSelector: {}
# -- Tolerations
tolerations: []
# -- Affinity rules
affinity: {}

# ==============================================================================
# Astromesh Configuration (mounted as ConfigMaps)
# ==============================================================================
config:
  # -- runtime.yaml content
  runtime: |
    apiVersion: astromesh/v1
    kind: RuntimeConfig
    metadata:
      name: default
    spec:
      api:
        host: "0.0.0.0"
        port: 8000
      defaults:
        orchestration:
          pattern: react
          max_iterations: 10

  # -- providers.yaml content
  providers: |
    apiVersion: astromesh/v1
    kind: ProviderConfig
    metadata:
      name: default-providers
    spec:
      providers:
        ollama:
          type: ollama
          endpoint: "http://ollama:11434"
          models:
            - "llama3.1:8b"
          health_check_interval: 30
        openai:
          type: openai_compat
          endpoint: "https://api.openai.com/v1"
          api_key_env: OPENAI_API_KEY
          models:
            - "gpt-4o"
            - "gpt-4o-mini"
      routing:
        default_strategy: cost_optimized
        fallback_enabled: true
        circuit_breaker:
          failure_threshold: 3
          recovery_timeout: 60

  # -- channels.yaml content
  channels: |
    channels:
      whatsapp:
        verify_token: "${WHATSAPP_VERIFY_TOKEN}"
        access_token: "${WHATSAPP_ACCESS_TOKEN}"
        phone_number_id: "${WHATSAPP_PHONE_NUMBER_ID}"
        app_secret: "${WHATSAPP_APP_SECRET}"
        default_agent: "whatsapp-assistant"
        rate_limit:
          window_seconds: 60
          max_messages: 30

  # -- Agent YAML files (key = filename, value = content)
  agents: {}
    # support-agent.agent.yaml: |
    #   apiVersion: astromesh/v1
    #   kind: Agent
    #   ...

# ==============================================================================
# Secrets
# ==============================================================================
secrets:
  # -- Create a Secret resource
  create: true
  # -- Use an existing Secret instead
  existingSecret: ""
  # -- Secret values (only used if create=true)
  values:
    OPENAI_API_KEY: ""
    WHATSAPP_VERIFY_TOKEN: ""
    WHATSAPP_ACCESS_TOKEN: ""
    WHATSAPP_PHONE_NUMBER_ID: ""
    WHATSAPP_APP_SECRET: ""

# ==============================================================================
# Observability
# ==============================================================================
observability:
  prometheus:
    # -- Add Prometheus scrape annotations to Service
    enabled: true
  otel:
    # -- Enable OpenTelemetry environment variables
    enabled: false
    # -- OTel collector gRPC endpoint
    endpoint: "http://otel-collector:4317"

# ==============================================================================
# External Database (when postgresql.enabled=false)
# ==============================================================================
externalDatabase:
  # -- External PostgreSQL host
  host: ""
  # -- External PostgreSQL port
  port: "5432"
  # -- External PostgreSQL database name
  database: "astromesh"
  # -- External PostgreSQL username
  username: "astromesh"
  # -- Name of existing Secret with key `DATABASE_PASSWORD`
  existingSecret: ""

# ==============================================================================
# External Redis (when redis.enabled=false)
# ==============================================================================
externalRedis:
  # -- External Redis host
  host: ""
  # -- External Redis port
  port: "6379"
  # -- Name of existing Secret with key `REDIS_PASSWORD`
  existingSecret: ""

# ==============================================================================
# Subchart: PostgreSQL (Bitnami)
# ==============================================================================
postgresql:
  enabled: true
  auth:
    database: astromesh
    username: astromesh
    password: "astromesh"
  primary:
    persistence:
      size: 10Gi

# ==============================================================================
# Subchart: Redis (Bitnami)
# ==============================================================================
redis:
  enabled: true
  architecture: standalone
  auth:
    enabled: false

# ==============================================================================
# Subchart: Ollama
# ==============================================================================
ollama:
  enabled: false
```

**Step 2: Commit**

```bash
git add deploy/helm/astromesh/values.yaml
git commit -m "feat(helm): add values.yaml with full default configuration"
```

---

### Task 3: ConfigMap Templates

**Files:**
- Create: `deploy/helm/astromesh/templates/configmap-runtime.yaml`
- Create: `deploy/helm/astromesh/templates/configmap-providers.yaml`
- Create: `deploy/helm/astromesh/templates/configmap-channels.yaml`
- Create: `deploy/helm/astromesh/templates/configmap-agents.yaml`

**Step 1: Create configmap-runtime.yaml**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "astromesh.fullname" . }}-runtime
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
data:
  runtime.yaml: |
    {{- .Values.config.runtime | nindent 4 }}
```

**Step 2: Create configmap-providers.yaml**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "astromesh.fullname" . }}-providers
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
data:
  providers.yaml: |
    {{- .Values.config.providers | nindent 4 }}
```

**Step 3: Create configmap-channels.yaml**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "astromesh.fullname" . }}-channels
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
data:
  channels.yaml: |
    {{- .Values.config.channels | nindent 4 }}
```

**Step 4: Create configmap-agents.yaml**

```yaml
{{- if .Values.config.agents }}
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "astromesh.fullname" . }}-agents
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
data:
  {{- range $filename, $content := .Values.config.agents }}
  {{ $filename }}: |
    {{- $content | nindent 4 }}
  {{- end }}
{{- end }}
```

**Step 5: Commit**

```bash
git add deploy/helm/astromesh/templates/configmap-*.yaml
git commit -m "feat(helm): add ConfigMap templates for runtime, providers, channels, agents"
```

---

### Task 4: Secret Template

**Files:**
- Create: `deploy/helm/astromesh/templates/secret.yaml`

**Step 1: Create secret.yaml**

```yaml
{{- if .Values.secrets.create }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "astromesh.fullname" . }}
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
type: Opaque
data:
  {{- range $key, $value := .Values.secrets.values }}
  {{- if $value }}
  {{ $key }}: {{ $value | b64enc | quote }}
  {{- end }}
  {{- end }}
{{- end }}
```

**Step 2: Commit**

```bash
git add deploy/helm/astromesh/templates/secret.yaml
git commit -m "feat(helm): add Secret template with base64 encoding"
```

---

### Task 5: ServiceAccount Template

**Files:**
- Create: `deploy/helm/astromesh/templates/serviceaccount.yaml`

**Step 1: Create serviceaccount.yaml**

```yaml
{{- if .Values.serviceAccount.create -}}
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "astromesh.serviceAccountName" . }}
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
  {{- with .Values.serviceAccount.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
automountServiceAccountToken: false
{{- end }}
```

**Step 2: Commit**

```bash
git add deploy/helm/astromesh/templates/serviceaccount.yaml
git commit -m "feat(helm): add ServiceAccount template"
```

---

### Task 6: Deployment Template

**Files:**
- Create: `deploy/helm/astromesh/templates/deployment.yaml`

**Step 1: Create deployment.yaml**

This is the core template. It mounts all ConfigMaps, injects secrets as env vars, sets up probes, and configures resources.

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "astromesh.fullname" . }}
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
spec:
  {{- if not .Values.autoscaling.enabled }}
  replicas: {{ .Values.replicaCount }}
  {{- end }}
  selector:
    matchLabels:
      {{- include "astromesh.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      annotations:
        checksum/config-runtime: {{ include (print $.Template.BasePath "/configmap-runtime.yaml") . | sha256sum }}
        checksum/config-providers: {{ include (print $.Template.BasePath "/configmap-providers.yaml") . | sha256sum }}
        checksum/config-channels: {{ include (print $.Template.BasePath "/configmap-channels.yaml") . | sha256sum }}
      {{- with .Values.podAnnotations }}
        {{- toYaml . | nindent 8 }}
      {{- end }}
      labels:
        {{- include "astromesh.selectorLabels" . | nindent 8 }}
    spec:
      {{- with .Values.imagePullSecrets }}
      imagePullSecrets:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      serviceAccountName: {{ include "astromesh.serviceAccountName" . }}
      {{- with .Values.podSecurityContext }}
      securityContext:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      containers:
        - name: {{ .Chart.Name }}
          {{- with .Values.securityContext }}
          securityContext:
            {{- toYaml . | nindent 12 }}
          {{- end }}
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - name: http
              containerPort: 8000
              protocol: TCP
          livenessProbe:
            httpGet:
              path: /v1/health
              port: http
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /v1/health
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
          env:
            - name: ASTROMESH_CONFIG_DIR
              value: /app/config
            # -- PostgreSQL connection
            - name: DATABASE_HOST
              value: {{ include "astromesh.postgresql.host" . | quote }}
            - name: DATABASE_PORT
              value: {{ include "astromesh.postgresql.port" . | quote }}
            - name: DATABASE_NAME
              value: {{ .Values.postgresql.auth.database | default .Values.externalDatabase.database | quote }}
            - name: DATABASE_USER
              value: {{ .Values.postgresql.auth.username | default .Values.externalDatabase.username | quote }}
            {{- if .Values.postgresql.enabled }}
            - name: DATABASE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ include "astromesh.fullname" . }}-postgresql
                  key: password
            {{- else if .Values.externalDatabase.existingSecret }}
            - name: DATABASE_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalDatabase.existingSecret }}
                  key: DATABASE_PASSWORD
            {{- end }}
            # -- Redis connection
            - name: REDIS_HOST
              value: {{ include "astromesh.redis.host" . | quote }}
            - name: REDIS_PORT
              value: {{ include "astromesh.redis.port" . | quote }}
            {{- if and (not .Values.redis.enabled) .Values.externalRedis.existingSecret }}
            - name: REDIS_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: {{ .Values.externalRedis.existingSecret }}
                  key: REDIS_PASSWORD
            {{- end }}
            # -- Secrets (API keys, tokens)
            {{- $secretName := default (include "astromesh.fullname" .) .Values.secrets.existingSecret }}
            {{- range $key, $value := .Values.secrets.values }}
            {{- if $value }}
            - name: {{ $key }}
              valueFrom:
                secretKeyRef:
                  name: {{ $secretName }}
                  key: {{ $key }}
            {{- end }}
            {{- end }}
            # -- OpenTelemetry
            {{- if .Values.observability.otel.enabled }}
            - name: OTEL_EXPORTER_OTLP_ENDPOINT
              value: {{ .Values.observability.otel.endpoint | quote }}
            - name: OTEL_SERVICE_NAME
              value: {{ include "astromesh.fullname" . | quote }}
            {{- end }}
          volumeMounts:
            - name: config-runtime
              mountPath: /app/config/runtime.yaml
              subPath: runtime.yaml
              readOnly: true
            - name: config-providers
              mountPath: /app/config/providers.yaml
              subPath: providers.yaml
              readOnly: true
            - name: config-channels
              mountPath: /app/config/channels.yaml
              subPath: channels.yaml
              readOnly: true
            {{- if .Values.config.agents }}
            - name: config-agents
              mountPath: /app/config/agents
              readOnly: true
            {{- end }}
          {{- with .Values.resources }}
          resources:
            {{- toYaml . | nindent 12 }}
          {{- end }}
      volumes:
        - name: config-runtime
          configMap:
            name: {{ include "astromesh.fullname" . }}-runtime
        - name: config-providers
          configMap:
            name: {{ include "astromesh.fullname" . }}-providers
        - name: config-channels
          configMap:
            name: {{ include "astromesh.fullname" . }}-channels
        {{- if .Values.config.agents }}
        - name: config-agents
          configMap:
            name: {{ include "astromesh.fullname" . }}-agents
        {{- end }}
      {{- with .Values.nodeSelector }}
      nodeSelector:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.affinity }}
      affinity:
        {{- toYaml . | nindent 8 }}
      {{- end }}
      {{- with .Values.tolerations }}
      tolerations:
        {{- toYaml . | nindent 8 }}
      {{- end }}
```

**Step 2: Commit**

```bash
git add deploy/helm/astromesh/templates/deployment.yaml
git commit -m "feat(helm): add Deployment template with config mounts, probes, and env vars"
```

---

### Task 7: Service Template

**Files:**
- Create: `deploy/helm/astromesh/templates/service.yaml`

**Step 1: Create service.yaml**

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "astromesh.fullname" . }}
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
  {{- if .Values.observability.prometheus.enabled }}
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
  {{- end }}
spec:
  type: {{ .Values.service.type }}
  ports:
    - port: {{ .Values.service.port }}
      targetPort: http
      protocol: TCP
      name: http
  selector:
    {{- include "astromesh.selectorLabels" . | nindent 4 }}
```

**Step 2: Commit**

```bash
git add deploy/helm/astromesh/templates/service.yaml
git commit -m "feat(helm): add Service template with Prometheus annotations"
```

---

### Task 8: Ingress Template

**Files:**
- Create: `deploy/helm/astromesh/templates/ingress.yaml`

**Step 1: Create ingress.yaml**

```yaml
{{- if .Values.ingress.enabled -}}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "astromesh.fullname" . }}
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
  {{- with .Values.ingress.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- if .Values.ingress.className }}
  ingressClassName: {{ .Values.ingress.className }}
  {{- end }}
  {{- if .Values.ingress.tls }}
  tls:
    {{- range .Values.ingress.tls }}
    - hosts:
        {{- range .hosts }}
        - {{ . | quote }}
        {{- end }}
      secretName: {{ .secretName }}
    {{- end }}
  {{- end }}
  rules:
    {{- range .Values.ingress.hosts }}
    - host: {{ .host | quote }}
      http:
        paths:
          {{- range .paths }}
          - path: {{ .path }}
            pathType: {{ .pathType }}
            backend:
              service:
                name: {{ include "astromesh.fullname" $ }}
                port:
                  name: http
          {{- end }}
    {{- end }}
{{- end }}
```

**Step 2: Commit**

```bash
git add deploy/helm/astromesh/templates/ingress.yaml
git commit -m "feat(helm): add Ingress template"
```

---

### Task 9: HPA Template

**Files:**
- Create: `deploy/helm/astromesh/templates/hpa.yaml`

**Step 1: Create hpa.yaml**

```yaml
{{- if .Values.autoscaling.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "astromesh.fullname" . }}
  labels:
    {{- include "astromesh.labels" . | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "astromesh.fullname" . }}
  minReplicas: {{ .Values.autoscaling.minReplicas }}
  maxReplicas: {{ .Values.autoscaling.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.autoscaling.targetCPUUtilizationPercentage }}
{{- end }}
```

**Step 2: Commit**

```bash
git add deploy/helm/astromesh/templates/hpa.yaml
git commit -m "feat(helm): add HorizontalPodAutoscaler template"
```

---

### Task 10: NOTES.txt

**Files:**
- Create: `deploy/helm/astromesh/templates/NOTES.txt`

**Step 1: Create NOTES.txt**

```
=== Astromesh Agent Runtime ===

{{- if .Values.ingress.enabled }}
Access the API at:
{{- range .Values.ingress.hosts }}
  http{{ if $.Values.ingress.tls }}s{{ end }}://{{ .host }}
{{- end }}
{{- else }}
Get the application URL by running:
  export POD_NAME=$(kubectl get pods --namespace {{ .Release.Namespace }} -l "{{ include "astromesh.selectorLabels" . | replace "\n" "," }}" -o jsonpath="{.items[0].metadata.name}")
  kubectl --namespace {{ .Release.Namespace }} port-forward $POD_NAME 8000:8000

Then visit: http://localhost:8000/v1/health
{{- end }}

{{- if .Values.postgresql.enabled }}
PostgreSQL: {{ include "astromesh.postgresql.host" . }}:5432
{{- end }}

{{- if .Values.redis.enabled }}
Redis: {{ include "astromesh.redis.host" . }}:6379
{{- end }}

{{- if .Values.ollama.enabled }}
Ollama: {{ .Release.Name }}-ollama:11434
{{- end }}
```

**Step 2: Commit**

```bash
git add deploy/helm/astromesh/templates/NOTES.txt
git commit -m "feat(helm): add NOTES.txt post-install instructions"
```

---

### Task 11: Environment Values Overrides

**Files:**
- Create: `deploy/helm/astromesh/values-dev.yaml`
- Create: `deploy/helm/astromesh/values-staging.yaml`
- Create: `deploy/helm/astromesh/values-prod.yaml`

**Step 1: Create values-dev.yaml**

```yaml
# Development environment overrides
replicaCount: 1

resources:
  requests:
    cpu: 250m
    memory: 512Mi
  limits:
    cpu: "1"
    memory: 1Gi

postgresql:
  enabled: true
  auth:
    password: "dev-password"

redis:
  enabled: true

ollama:
  enabled: true
```

**Step 2: Create values-staging.yaml**

```yaml
# Staging environment overrides
replicaCount: 2

resources:
  requests:
    cpu: 500m
    memory: 1Gi
  limits:
    cpu: "2"
    memory: 2Gi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 4
  targetCPUUtilizationPercentage: 75

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: astromesh-staging.example.com
      paths:
        - path: /
          pathType: Prefix

postgresql:
  enabled: true
  auth:
    password: ""  # Use existingSecret in practice

redis:
  enabled: true
```

**Step 3: Create values-prod.yaml**

```yaml
# Production environment overrides
replicaCount: 3

resources:
  requests:
    cpu: "1"
    memory: 2Gi
  limits:
    cpu: "4"
    memory: 4Gi

autoscaling:
  enabled: true
  minReplicas: 3
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
  hosts:
    - host: astromesh.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: astromesh-tls
      hosts:
        - astromesh.example.com

# Use external managed databases in production
postgresql:
  enabled: false
externalDatabase:
  host: "your-rds-instance.region.rds.amazonaws.com"
  port: "5432"
  database: astromesh
  username: astromesh
  existingSecret: astromesh-db-credentials

redis:
  enabled: false
externalRedis:
  host: "your-elasticache.region.cache.amazonaws.com"
  port: "6379"

secrets:
  create: false
  existingSecret: astromesh-secrets

observability:
  prometheus:
    enabled: true
  otel:
    enabled: true
    endpoint: "http://otel-collector.monitoring:4317"
```

**Step 4: Commit**

```bash
git add deploy/helm/astromesh/values-dev.yaml deploy/helm/astromesh/values-staging.yaml deploy/helm/astromesh/values-prod.yaml
git commit -m "feat(helm): add environment-specific values for dev, staging, prod"
```

---

### Task 12: Build Dependencies and Validate

**Step 1: Add Helm dependencies**

```bash
cd deploy/helm/astromesh && helm dependency update
```

This downloads Bitnami PostgreSQL, Redis, and Ollama charts into `charts/`.

**Step 2: Lint the chart**

```bash
helm lint deploy/helm/astromesh
```

Expected: `1 chart(s) linted, 0 chart(s) failed`

**Step 3: Template render test (dry-run)**

```bash
helm template test-release deploy/helm/astromesh
```

Expected: All templates render without errors. Verify:
- Deployment has correct volume mounts
- ConfigMaps contain the YAML config
- Secret has base64 values
- Service has Prometheus annotations
- Ingress is NOT rendered (disabled by default)
- HPA is NOT rendered (disabled by default)

**Step 4: Template render with dev values**

```bash
helm template test-release deploy/helm/astromesh -f deploy/helm/astromesh/values-dev.yaml
```

Expected: Ollama resources appear (enabled in dev).

**Step 5: Template render with prod values**

```bash
helm template test-release deploy/helm/astromesh -f deploy/helm/astromesh/values-prod.yaml
```

Expected: Ingress and HPA rendered. No PostgreSQL/Redis subcharts. External database env vars set.

**Step 6: Add charts/ to .gitignore for the subchart tarballs**

Create `deploy/helm/astromesh/charts/.gitkeep` but add `deploy/helm/astromesh/charts/*.tgz` to the repo `.gitignore`.

**Step 7: Commit**

```bash
git add deploy/helm/astromesh/charts/.gitkeep .gitignore
git commit -m "feat(helm): validate chart lint and template rendering"
```

---

### Task 13: Final Review and Summary Commit

**Step 1: Verify complete file tree**

```bash
find deploy/helm -type f | sort
```

Expected:
```
deploy/helm/astromesh/.helmignore
deploy/helm/astromesh/Chart.yaml
deploy/helm/astromesh/charts/.gitkeep
deploy/helm/astromesh/templates/NOTES.txt
deploy/helm/astromesh/templates/_helpers.tpl
deploy/helm/astromesh/templates/configmap-agents.yaml
deploy/helm/astromesh/templates/configmap-channels.yaml
deploy/helm/astromesh/templates/configmap-providers.yaml
deploy/helm/astromesh/templates/configmap-runtime.yaml
deploy/helm/astromesh/templates/deployment.yaml
deploy/helm/astromesh/templates/hpa.yaml
deploy/helm/astromesh/templates/ingress.yaml
deploy/helm/astromesh/templates/secret.yaml
deploy/helm/astromesh/templates/service.yaml
deploy/helm/astromesh/templates/serviceaccount.yaml
deploy/helm/astromesh/values-dev.yaml
deploy/helm/astromesh/values-prod.yaml
deploy/helm/astromesh/values-staging.yaml
deploy/helm/astromesh/values.yaml
```

**Step 2: Verify no secrets leaked**

Ensure no real API keys or passwords are hardcoded in any committed file.

**Step 3: Run final lint**

```bash
helm lint deploy/helm/astromesh
helm lint deploy/helm/astromesh -f deploy/helm/astromesh/values-dev.yaml
helm lint deploy/helm/astromesh -f deploy/helm/astromesh/values-prod.yaml
```

All must pass.
