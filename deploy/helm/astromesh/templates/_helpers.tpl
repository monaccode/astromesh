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

{{/*
OTel collector endpoint — auto-wire to subchart or use manual config
*/}}
{{- define "astromesh.otel.endpoint" -}}
{{- if (index .Values "opentelemetry-collector" "enabled") }}
{{- printf "http://%s-opentelemetry-collector:4317" .Release.Name }}
{{- else }}
{{- .Values.observability.otel.endpoint }}
{{- end }}
{{- end }}
