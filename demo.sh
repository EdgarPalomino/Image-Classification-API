# Switch to HPA mode
kubectl patch deployment ml-api -n ml-api --type='merge' -p '{"spec":{"replicas":2}}'
helm upgrade ml-api charts/ml-api -n ml-api --set autoscaling.mode=hpa

# Watch HPA (Terminal 1)
kubectl get hpa -n ml-api -w

# Watch pods (Terminal 2)
kubectl get pods -n ml-api -w

# Check HPA status
kubectl get hpa -n ml-api

# ==========================================
# VPA Demo
# ==========================================

# Switch to VPA mode

it clone --depth 1 https://github.com/kubernetes/autoscaler.git /tmp/autoscaler
  cd /tmp/autoscaler/vertical-pod-autoscaler && ./pkg/admission-controller/gencerts.sh

  # 2. Restart admission controller
  kubectl delete pod -n kube-system -l app=vpa-admission-controller

  # 3. Switch to VPA mode
  kubectl patch deployment ml-api -n ml-api --type='merge' -p '{"spec":{"replicas":2}}'
helm upgrade ml-api /Users/aiko/Documents/school/cse_4207/finalproject-apple/charts/ml-api -n ml-api --set autoscaling.mode=vpa

  # 4. Delete pods to apply VPA resources
  kubectl delete pod -n ml-api -l app.kubernetes.io/name=ml-api

  # 5. Restart port-forward
  kubectl port-forward svc/ml-api 8001:80 -n ml-api &

  # 6. Verify
  kubectl get vpa -n ml-api
  kubectl get pods -n ml-api -o custom-columns="NAME:.metadata.name,CPU:.spec.containers[0].resources.requests.cpu,MEM:.spec.containers[0].resources.requests.memory"