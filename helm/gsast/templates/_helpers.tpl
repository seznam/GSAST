{{/*
Expand the name of the chart.
*/}}
{{- define "gsast.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "gsast.fullname" -}}
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
{{- define "gsast.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "gsast.labels" -}}
helm.sh/chart: {{ include "gsast.chart" . }}
{{ include "gsast.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Values.internal.enabled }}
{{- with .Values.internal.labels }}
{{ toYaml . }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "gsast.selectorLabels" -}}
app.kubernetes.io/name: {{ include "gsast.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Common environment variables for both API and Worker
*/}}
{{- define "gsast.commonEnv" -}}
{{- if .Values.environment.httpProxy }}
- name: http_proxy
  value: {{ .Values.environment.httpProxy }}
- name: HTTP_PROXY
  value: {{ .Values.environment.httpProxy }}
{{- end }}
{{- if .Values.environment.httpsProxy }}
- name: https_proxy
  value: {{ .Values.environment.httpsProxy }}
- name: HTTPS_PROXY
  value: {{ .Values.environment.httpsProxy }}
{{- end }}
{{- if .Values.environment.noProxy }}
- name: no_proxy
  value: {{ .Values.environment.noProxy }}
- name: NO_PROXY
  value: {{ .Values.environment.noProxy }}
{{- end }}
- name: GITHUB_API_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.existingSecret | default (printf "%s-secret" (include "gsast.fullname" .)) }}
      key: GITHUB_API_TOKEN
- name: GITLAB_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.existingSecret | default (printf "%s-secret" (include "gsast.fullname" .)) }}
      key: GITLAB_URL
- name: GITLAB_API_TOKEN
  valueFrom:
    secretKeyRef:
      name: {{ .Values.existingSecret | default (printf "%s-secret" (include "gsast.fullname" .)) }}
      key: GITLAB_API_TOKEN
{{- if .Values.redis.enabled }}
- name: REDIS_URL
  value: "redis://:$(REDIS_PASSWORD)@{{ include "gsast.fullname" . }}-redis-master:6379"
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "gsast.fullname" . }}-redis
      key: redis-password
{{- else }}
- name: REDIS_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.existingSecret | default (printf "%s-secret" (include "gsast.fullname" .)) }}
      key: REDIS_URL
{{- end }}
{{- end }}

{{/*
Custom GitLab CA volumes
*/}}
{{- define "gsast.caVolumes" -}}
{{- if .Values.environment.customGitlabCA.enabled }}
volumes:
  - name: custom-gitlab-ca
    configMap:
      name: {{ .Values.environment.customGitlabCA.configMapName }}
{{- end }}
{{- end }}

{{/*
Custom GitLab CA volume mounts and environment variables
*/}}
{{- define "gsast.caVolumeMounts" -}}
{{- if .Values.environment.customGitlabCA.enabled }}
- name: REQUESTS_CA_BUNDLE
  value: {{ .Values.environment.customGitlabCA.caMountPath }}{{ .Values.environment.customGitlabCA.caFile }}
- name: SSL_CERT_FILE
  value: {{ .Values.environment.customGitlabCA.caMountPath }}{{ .Values.environment.customGitlabCA.caFile }}
- name: GIT_SSL_CAINFO
  value: {{ .Values.environment.customGitlabCA.caMountPath }}{{ .Values.environment.customGitlabCA.caFile }}
{{- end }}
{{- end }}

