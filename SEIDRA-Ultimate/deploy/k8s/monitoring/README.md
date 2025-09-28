# Stack observabilité (Kubernetes)

Ce dossier fournit des valeurs Helm pour déployer Prometheus, Grafana et Loki dans un namespace Kubernetes dédié (`observability` recommandé). Les charts officiels sont utilisés et complétés par les tableaux de bord, alertes et règles présents dans `monitoring/`. Toutes les commandes ci-dessous sont à exécuter depuis la racine `SEIDRA-Ultimate/`.

## Pré-requis

- `kubectl` et `helm` installés localement.
- Namespace créé : `kubectl create namespace observability`.
- Accès aux charts :
  - `helm repo add prometheus-community https://prometheus-community.github.io/helm-charts`
  - `helm repo add grafana https://grafana.github.io/helm-charts`

## Prometheus

Fichier : [`values-prometheus.yaml`](values-prometheus.yaml)

- Active le scraping des services `backend`, `worker`, `flower`, `tempo` exposés sur le cluster.
- Charge les alertes depuis `monitoring/prometheus/alerts.yml` via un ConfigMap `seidra-prometheus-alerts`.
- Expose Prometheus en `ClusterIP` (ajoutez un Ingress si nécessaire).

Commande :

```bash
kubectl create configmap seidra-prometheus-config \
  --namespace observability \
  --from-file=prometheus.yml=monitoring/prometheus/prometheus.yml \
  --from-file=alerts.yml=monitoring/prometheus/alerts.yml --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install prometheus prometheus-community/prometheus \
  --namespace observability \
  -f deploy/k8s/monitoring/values-prometheus.yaml
```

## Loki

Fichier : [`values-loki.yaml`](values-loki.yaml)

- Configure Loki en mode simple avec persistance.
- Déploie Promtail en DaemonSet pour l'ingestion des logs applicatifs.
- Prépare un service `ClusterIP` consommé par Grafana.

Commande :

```bash
helm upgrade --install loki grafana/loki-stack \
  --namespace observability \
  -f deploy/k8s/monitoring/values-loki.yaml
```

## Grafana

Fichier : [`values-grafana.yaml`](values-grafana.yaml)

- Provisionne les datasources Prometheus, Loki, Tempo.
- Ajoute les dashboards du dépôt (ConfigMap `seidra-grafana-dashboards`).
- Active l'unified alerting avec les règles `monitoring/grafana/provisioning/alerting/rules.yml`.
- Définit un mot de passe admin via `GRAFANA_ADMIN_PASSWORD` (modifiez la valeur avant installation).

Commande :

```bash
kubectl create configmap seidra-grafana-dashboards \
  --namespace observability \
  --from-file=monitoring/grafana/provisioning/dashboards --dry-run=client -o yaml | kubectl apply -f -
kubectl label configmap seidra-grafana-dashboards grafana_dashboard=seidra --namespace observability --overwrite

kubectl create configmap seidra-grafana-alerting \
  --namespace observability \
  --from-file=monitoring/grafana/provisioning/alerting --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install grafana grafana/grafana \
  --namespace observability \
  -f deploy/k8s/monitoring/values-grafana.yaml
```

## Accès & exploitation

- Grafana : `kubectl port-forward svc/grafana 3001:80 -n observability`
- Prometheus : `kubectl port-forward svc/prometheus-server 9090:80 -n observability`
- Loki : accessible via Grafana (`Explore > Logs`)

Complétez ces procédures avec le runbook (`monitoring/runbook.md`) et le guide d'exploitation (`doc/guide_exploitation_observabilite.md`) pour connaître les playbooks d'alerte et de remédiation.
