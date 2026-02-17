#!/bin/bash

set -e

echo "=========================================="
echo "  ML API Project Startup Script"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Step 1: Start Minikube (fresh start to avoid stale state)
print_status "Starting Minikube..."
if minikube status 2>/dev/null | grep -q "Running"; then
    print_status "Minikube is already running"
else
    # Delete any stale minikube state first
    minikube delete 2>/dev/null || true
    minikube start --driver=docker --memory=6144 --cpus=4
fi

# Step 2: Enable required addons
print_status "Enabling Minikube addons..."
minikube addons enable ingress
minikube addons enable metrics-server

# Step 3: Install VPA (Vertical Pod Autoscaler)
print_status "Installing Vertical Pod Autoscaler..."
if ! kubectl get crd verticalpodautoscalers.autoscaling.k8s.io >/dev/null 2>&1; then
    rm -rf /tmp/autoscaler 2>/dev/null
    git clone --depth 1 --branch master https://github.com/kubernetes/autoscaler.git /tmp/autoscaler 2>/dev/null
    kubectl apply -f /tmp/autoscaler/vertical-pod-autoscaler/deploy/vpa-v1-crd-gen.yaml 2>/dev/null
    kubectl apply -f /tmp/autoscaler/vertical-pod-autoscaler/deploy/ 2>/dev/null || true
    rm -rf /tmp/autoscaler
else
    print_status "VPA already installed"
fi

# Step 4: Build Docker image
print_status "Building Docker image..."
docker build -t ml-api:v1.0 .

# Step 4: Load image into Minikube
print_status "Loading image into Minikube..."
minikube image load ml-api:v1.0

# Step 5: Add Helm repo and update
print_status "Setting up Helm repositories..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
helm repo update

# Step 6: Install Prometheus + Grafana monitoring stack
print_status "Installing monitoring stack (Prometheus + Grafana)..."
if helm list -n monitoring 2>/dev/null | grep -q "monitoring"; then
    print_status "Monitoring stack already installed, upgrading..."
    helm upgrade monitoring prometheus-community/kube-prometheus-stack -n monitoring
else
    helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
fi

# Step 7: Apply custom Grafana dashboard
print_status "Applying custom Grafana dashboard..."
kubectl apply -f k8s/grafana-dashboard.yaml

# Step 8: Deploy ML API via Helm
print_status "Deploying ML API via Helm..."
helm upgrade --install ml-api charts/ml-api -n ml-api --create-namespace

# Step 9: Wait for pods to be ready
print_status "Waiting for pods to be ready (this may take a few minutes)..."

echo "Waiting for Grafana..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=grafana -n monitoring --timeout=300s || print_warning "Grafana pods may still be starting..."

echo "Waiting for ML API..."
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=ml-api -n ml-api --timeout=300s || print_warning "ML API pods may still be starting..."

# Step 10: Show deployment status
echo ""
print_status "Deployment Status:"
echo "----------------------------------------"
echo "ML API Namespace:"
kubectl get pods,svc,hpa -n ml-api
echo ""
echo "Monitoring Namespace (first 10 pods):"
kubectl get pods -n monitoring | head -10
echo ""

# Step 11: Get Grafana password
echo "=========================================="
print_status "Grafana Credentials:"
echo "  Username: admin"
echo -n "  Password: "
kubectl --namespace monitoring get secrets monitoring-grafana -o jsonpath="{.data.admin-password}" | base64 -d
echo ""
echo "=========================================="

# Step 12: Start port forwarding in background
print_status "Starting port forwarding..."

# Kill any existing port-forward processes for these ports
pkill -f "port-forward.*8001" 2>/dev/null || true
pkill -f "port-forward.*3000" 2>/dev/null || true

sleep 2

# Port forward ML API to 8001
kubectl port-forward svc/ml-api 8001:80 -n ml-api &
PF_API_PID=$!

# Port forward Grafana to 3000
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring &
PF_GRAFANA_PID=$!

sleep 3

echo ""
echo "=========================================="
print_status "Services are now available:"
echo "  ML API:       http://localhost:8001"
echo "  API Docs:     http://localhost:8001/docs"
echo "  Health UI:    http://localhost:8001/health-ui"
echo "  Grafana:      http://localhost:3000"
echo "=========================================="
echo ""
print_status "Port forwarding is running in the background."
print_status "Press Ctrl+C to stop port forwarding, or run ./cleanup.sh to clean up everything."
echo ""

# Wait for port-forward processes
wait $PF_API_PID $PF_GRAFANA_PID
