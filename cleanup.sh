#!/bin/bash

echo "=========================================="
echo "  ML API Project Cleanup Script"
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

# Step 1: Kill port-forward processes
print_status "Stopping port forwarding..."
pkill -f "port-forward.*8001" 2>/dev/null || true
pkill -f "port-forward.*3000" 2>/dev/null || true
pkill -f "kubectl port-forward" 2>/dev/null || true

# Step 2: Uninstall Helm releases (only if minikube is running)
if minikube status 2>/dev/null | grep -q "Running"; then
    print_status "Uninstalling Helm releases..."
    helm uninstall ml-api -n ml-api 2>/dev/null || print_warning "ml-api release not found"
    helm uninstall monitoring -n monitoring 2>/dev/null || print_warning "monitoring release not found"

    # Step 3: Delete namespaces
    print_status "Deleting Kubernetes namespaces..."
    kubectl delete namespace ml-api --ignore-not-found=true 2>/dev/null || true
    kubectl delete namespace monitoring --ignore-not-found=true 2>/dev/null || true
fi

# Step 4: Delete Minikube completely (removes profile and container)
print_status "Deleting Minikube cluster..."
minikube delete 2>/dev/null || print_warning "Minikube cluster not found"

# Step 5: Clean up Docker resources (only project-related)
print_status "Cleaning up Docker resources..."
docker rmi ml-api:v1.0 2>/dev/null || true

# Step 6: Prune unused Docker resources
print_status "Pruning unused Docker resources..."
docker system prune -f 2>/dev/null || true

echo ""
echo "=========================================="
print_status "Cleanup complete!"
echo "  - Helm releases uninstalled"
echo "  - Kubernetes namespaces deleted"
echo "  - Minikube cluster deleted"
echo "  - Docker image removed"
echo ""
echo "  Run ./run.sh to start the project again."
echo "=========================================="
