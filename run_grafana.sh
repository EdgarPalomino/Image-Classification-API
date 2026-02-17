helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace

kubectl apply -f monitor.yaml
kubectl apply -f grafana-dashboard.yaml

kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring
