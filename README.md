# Image Classification API

A production-style **image classification REST API** built with FastAPI and an ONNX-exported YOLO11 classification model, packaged in Docker and deployed to **Kubernetes** with a Helm chart that supports **auto-scaling** (Horizontal and Vertical Pod Autoscaling) driven by live request load, plus a full **Prometheus + Grafana** observability stack.

The project was built to demonstrate an end-to-end cloud-native ML serving pipeline: containerize a model, deploy it behind a Service/Ingress, expose Prometheus metrics, and let Kubernetes automatically scale the number of pods (HPA) or the CPU/memory allocated to each pod (VPA) as traffic increases.

---

## Table of Contents

- [Demo Videos](#demo-videos)
- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Technology Stack & Role of Each Component](#technology-stack--role-of-each-component)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [Prerequisites](#prerequisites)
- [Running Locally (No Kubernetes)](#running-locally-no-kubernetes)
- [Running with Docker](#running-with-docker)
- [Running on Kubernetes (Full Stack)](#running-on-kubernetes-full-stack)
- [Switching Between HPA and VPA](#switching-between-hpa-and-vpa)
- [Load Testing / Demonstrating Autoscaling](#load-testing--demonstrating-autoscaling)
- [Monitoring & Dashboards](#monitoring--dashboards)
- [Testing](#testing)
- [Cleanup](#cleanup)

---

## Demo Videos

https://github.com/user-attachments/assets/cadb4681-693b-4bbd-a5e0-d274aa9d9a3b

https://github.com/user-attachments/assets/08534956-22bf-41d9-b028-43edac9e9e7e

---

## Features

- **FastAPI REST API** for image classification with automatic OpenAPI/Swagger docs.
- **ONNX Runtime inference** using a YOLO11-large classification model trained on ImageNet (1000 classes), returning the top-N predictions with confidence scores.
- **Kubernetes-native deployment** via a parameterized Helm chart (`charts/ml-api`), with `dev` and `prod` value overlays.
- **Horizontal Pod Autoscaler (HPA)** that scales pod replicas (2 → 20) based on CPU/memory utilization, with an aggressive scale-up / conservative scale-down policy tuned for demoing traffic bursts.
- **Vertical Pod Autoscaler (VPA)** as an alternative autoscaling mode that instead grows/shrinks each pod's CPU & memory requests.
- **Prometheus metrics** (`/metrics`) covering generic HTTP traffic and business-level prediction metrics (success/error counts, latency histograms), auto-discovered via a `ServiceMonitor`.
- **Grafana dashboard** provisioned automatically for visualizing request volume, latency percentiles, and error rates.
- **Kubernetes health probes** (liveness/readiness/startup) backed by a real model-loaded check, plus human-friendly `/health-ui` and `/metrics-ui` dashboards.
- **Model distribution via PersistentVolumeClaim**, populated by a Helm post-install/post-upgrade Job so the model artifact isn't baked permanently into a single pod's writable layer.
- **Traffic simulator** (`app/simulate_traffic.py`) to generate sustained load (and periodic invalid requests) against the deployed API to trigger and observe autoscaling in real time.
- **Automated pytest suite** covering health, prediction, and error-handling behavior via FastAPI's `TestClient`.
- **One-command environment bootstrap/teardown** (`run.sh` / `cleanup.sh`) that stands up Minikube, the monitoring stack, and the API, then tears it all down again.

---

## Architecture Overview

```
                                   ┌─────────────────────────┐
                                   │        Client            │
                                   │ (curl / browser / load   │
                                   │  generator script)        │
                                   └───────────┬──────────────┘
                                               │ HTTP
                                               ▼
                              ┌───────────────────────────────┐
                              │   nginx Ingress Controller     │
                              │      (ml-api.local)            │
                              └───────────────┬────────────────┘
                                               │
                                               ▼
                              ┌───────────────────────────────┐
                              │   Service: ml-api (ClusterIP)  │
                              └───────────────┬────────────────┘
                                               │ load-balanced
                     ┌─────────────────────────┼─────────────────────────┐
                     ▼                         ▼                         ▼
             ┌───────────────┐        ┌───────────────┐        ┌───────────────┐
             │  Pod: ml-api  │  ...   │  Pod: ml-api  │  ...   │  Pod: ml-api  │
             │  (FastAPI +   │        │  (FastAPI +   │        │  (FastAPI +   │
             │  ONNX Runtime)│        │  ONNX Runtime)│        │  ONNX Runtime)│
             └───────┬───────┘        └───────┬───────┘        └───────┬───────┘
                     │ model mounted from PVC (populated by init Job)  │
                     └──────────────────────────┬───────────────────────┘
                                                 │
                        ┌────────────────────────┴─────────────────────────┐
                        ▼                                                  ▼
        ┌───────────────────────────┐                     ┌───────────────────────────┐
        │ HorizontalPodAutoscaler    │  metrics-server     │ VerticalPodAutoscaler      │
        │ scales REPLICA COUNT       │◄────────────────────┤ scales POD CPU/MEMORY      │
        │ based on CPU/Mem %          │                     │ requests (alt. mode)       │
        └───────────────────────────┘                     └───────────────────────────┘

        ┌───────────────────────────────────────────────────────────────────────────┐
        │                          Observability Stack                               │
        │  ServiceMonitor  ──►  Prometheus  ──►  Grafana (dashboard + alerts)         │
        │  scrapes /metrics on every ml-api pod every 15s                            │
        └───────────────────────────────────────────────────────────────────────────┘
```

**Request flow:** a client sends an image to `/predict` → the Ingress/Service routes it to one of the running `ml-api` pods → the pod decodes and preprocesses the image with Pillow/NumPy → ONNX Runtime runs inference on the YOLO11 classification model → the top-5 predictions above the confidence threshold are returned as JSON, while Prometheus counters/histograms are updated for that request.

**Autoscaling flow:** the Kubernetes `metrics-server` continuously reports CPU/memory usage per pod. The **HPA** compares that against the target utilization (30% CPU / 70% memory by default) and adds/removes pod replicas; the **VPA** instead adjusts the CPU/memory *requests* of each pod's container. Only one mode is active at a time, selected via `autoscaling.mode` in the Helm values.

---

## Repository Structure

```
Image-Classification-API/
├── app/                              # FastAPI application source
│   ├── main.py                       # Routes, middleware, Prometheus metrics, startup/health checks
│   ├── litemodel.py                  # ONNX Runtime model wrapper — the inference backend actually used by main.py
│   ├── model.py                      # Alternative model wrapper using the Ultralytics YOLO Python API
│   ├── config.py                     # Pydantic Settings — env-driven app/model/server configuration
│   ├── schemas.py                    # Pydantic request/response models (predictions, health, errors)
│   ├── simulate_traffic.py           # Load-generator script used to trigger/demo autoscaling
│   ├── static/                       # Custom Swagger CSS, favicon
│   └── templates/                    # Jinja2 templates for /health-ui and /metrics-ui
│
├── models/
│   ├── yolo11l-cls.onnx              # YOLO11-large classification model, exported to ONNX
│   └── imagenet_classes.txt          # 1000 ImageNet class labels used to map prediction indices to names
│
├── images/                           # Sample images (bus.jpg, bolete_mushroom.webp) for manual/automated testing
│
├── tests/                            # Pytest suite
│   ├── conftest.py                   # Shared FastAPI TestClient fixture
│   ├── test_health.py                # /health endpoint behavior
│   ├── test_predict.py               # /predict happy-path classification
│   └── test_error_handling.py        # Invalid file type / bad input handling
│
├── charts/ml-api/                    # Helm chart — primary deployment mechanism
│   ├── Chart.yaml
│   ├── values.yaml                   # Base configuration (HPA/VPA, resources, ingress, config, etc.)
│   ├── values-dev.yaml               # Lightweight overrides for local/dev clusters
│   ├── values-prod.yaml              # Higher-resource, higher-availability overrides
│   └── templates/
│       ├── deployment.yaml           # Deployment + liveness/readiness/startup probes
│       ├── service.yaml              # ClusterIP Service
│       ├── hpa.yaml                  # HorizontalPodAutoscaler (active when autoscaling.mode=hpa)
│       ├── vpa.yaml                  # VerticalPodAutoscaler (active when autoscaling.mode=vpa)
│       ├── ingress.yaml              # Optional nginx Ingress resource
│       ├── configmap.yaml            # App configuration injected as env vars
│       ├── pvc.yaml                  # PersistentVolumeClaim for the model artifact
│       ├── model-init-job.yaml       # Post-install/upgrade Job that copies the model onto the PVC
│       ├── pdb.yaml                  # Optional PodDisruptionBudget
│       ├── servicemonitor.yaml       # Prometheus Operator ServiceMonitor for /metrics scraping
│       └── _helpers.tpl              # Shared naming/label template helpers
│
├── k8s/                               # Standalone, non-Helm reference manifests (namespace, deployment,
│                                       # service, ingress, HPA, ServiceMonitor, Grafana dashboard ConfigMap)
│
├── Dockerfile                         # Multi-stage build: builder (deps) + slim runtime image
├── requirements.txt                   # Python dependencies
├── rendered.yaml                      # Captured `helm template` output, kept for reference/diffing
│
├── run.sh                             # Bootstraps Minikube, VPA CRDs, monitoring stack, and the Helm release
├── cleanup.sh                         # Tears down Helm releases, namespaces, and the Minikube cluster
├── run_grafana.sh                     # Standalone script to (re)install Prometheus/Grafana and port-forward it
├── commands.txt / demo.sh / extra.txt # Cheat-sheets/snippets used while presenting HPA vs. VPA demos
│
└── README.md
```

---

## Technology Stack & Role of Each Component

| Technology | Role in this project |
|---|---|
| **FastAPI** | The web framework serving the REST API. Defines all routes (`/predict`, `/health`, `/metrics`, docs), request validation, dependency injection of settings, and automatic OpenAPI/Swagger (`/docs`) and ReDoc (`/redoc`) documentation. |
| **Uvicorn** | The ASGI server that actually runs the FastAPI application process inside the container (`uvicorn app.main:app`). |
| **Pydantic / pydantic-settings** | `app/schemas.py` defines strongly-typed request/response contracts (predictions, health, errors) that FastAPI validates and serializes automatically. `app/config.py` uses `pydantic-settings` to load configuration from environment variables (and `.env` locally), which is how the Helm-generated ConfigMap configures the app in-cluster. |
| **ONNX Runtime** | The primary inference engine (`app/litemodel.py`). Loads `models/yolo11l-cls.onnx` into a `CPUExecutionProvider` session, runs preprocessed image tensors through it, and returns raw class probabilities. Chosen over the full Ultralytics stack for a smaller runtime footprint in the container. |
| **Ultralytics (YOLO)** | Provides an alternative model wrapper (`app/model.py`) that loads and runs the same model via the Ultralytics Python API instead of raw ONNX Runtime. Not wired into `main.py` by default, but kept as a reference/fallback implementation and pulled in via `requirements.txt`. |
| **Pillow (PIL) / NumPy / OpenCV** | Handle image decoding from the uploaded bytes, color-mode normalization (e.g., RGBA → RGB), resizing to the model's expected input shape, and conversion to normalized `CHW` float tensors before inference. |
| **prometheus-client** | Instruments the API in-process: `Counter`/`Histogram` metrics for total requests, per-endpoint latency, and prediction success/error counts and latency, exposed as plain text on `/metrics` for scraping. |
| **Docker** | Packages the app into a reproducible image via a multi-stage `Dockerfile` (a `builder` stage compiles/installs Python deps into a venv, and a slim final stage copies just the venv + app + model, runs as a non-root user, and defines a container-level `HEALTHCHECK`). |
| **Kubernetes** | The runtime platform. Provides the `Deployment` (rolling updates, replica management), `Service` (stable internal networking), `Ingress` (external HTTP routing), `ConfigMap` (env-based configuration), `PersistentVolumeClaim` (model storage), and `PodDisruptionBudget` (availability guarantees during voluntary disruptions). |
| **Helm** | Templates and parameterizes all the Kubernetes manifests above into a single installable chart (`charts/ml-api`), with `values.yaml` plus `values-dev.yaml`/`values-prod.yaml` overlays so the same chart can be deployed differently per environment. |
| **Horizontal Pod Autoscaler (HPA)** | The main "scale based on request volume" mechanism. Watches CPU/memory utilization reported by `metrics-server` and adds/removes `ml-api` pod replicas (2–20 by default) using an asymmetric behavior policy: scale up fast (no stabilization delay, up to +6 pods per 10s or +200%) and scale down conservatively (30s stabilization, up to -4 pods per 15s) to absorb traffic spikes without flapping. |
| **Vertical Pod Autoscaler (VPA)** | An alternative autoscaling strategy that instead resizes each pod's CPU/memory *requests/limits* automatically based on observed usage, useful when the workload benefits more from "bigger pods" than "more pods." |
| **metrics-server** | The Kubernetes add-on that collects real-time CPU/memory usage per pod, which both the HPA and VPA rely on as their scaling signal. |
| **Minikube** | The local, single-node Kubernetes cluster used for development and demoing the full stack without a cloud provider. |
| **nginx Ingress Controller** | Terminates external HTTP traffic and routes it to the `ml-api` Service based on host/path rules defined in the Helm chart's `ingress.yaml`. |
| **Prometheus (kube-prometheus-stack)** | Scrapes the `/metrics` endpoint of every `ml-api` pod (auto-discovered through the `ServiceMonitor` custom resource) and stores the resulting time series for querying and alerting. |
| **Grafana** | Visualizes the Prometheus metrics through a pre-provisioned custom dashboard (`k8s/grafana-dashboard.yaml`), showing request volume, latency percentiles, and prediction success/error rates in real time — the same signals the HPA reacts to. |
| **pytest + FastAPI TestClient** | Powers the automated test suite (`tests/`), exercising the API in-process (no running server needed) to validate health checks, successful predictions, and graceful handling of invalid input. |

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Basic API info and a map of available endpoints. |
| `GET` | `/health` | Kubernetes liveness/readiness probe target. Returns `200` with `status: "healthy"` when the model is loaded, `503` otherwise. |
| `GET` | `/health-ui` | Human-friendly HTML health dashboard (uptime, model status, environment). Not used by Kubernetes probes. |
| `POST` | `/predict` | Accepts a `multipart/form-data` image upload (`file`), returns the top predictions with confidence scores. |
| `GET` | `/metrics` | Prometheus exposition-format metrics endpoint, scraped by the `ServiceMonitor`. |
| `GET` | `/metrics-ui` | Human-friendly HTML overview of what's being tracked (documentation, not a live metrics view). |
| `GET` | `/docs` | Swagger UI (interactive API docs), styled with a custom stylesheet. |
| `GET` | `/redoc` | ReDoc-based API documentation. |

### Example: classify an image

```bash
curl -X POST http://localhost:8001/predict \
  -F "file=@images/bus.jpg"
```

```json
{
  "success": true,
  "predictions": [
    { "class_name": "streetcar", "confidence": 0.7421 },
    { "class_name": "trolleybus", "confidence": 0.1187 }
  ],
  "model_version": "yolo11l-cls",
  "inference_time_ms": 42.31
}
```

Accepted file types: `.jpg`, `.jpeg`, `.png`, `.webp`. Max upload size: 10 MB (both configurable, see below).

---

## Configuration

All configuration is defined in [`app/config.py`](app/config.py) and can be overridden via environment variables (locally through a `.env` file, or in-cluster through the Helm-generated `ConfigMap`):

| Setting | Env Var | Default | Description |
|---|---|---|---|
| `app_name` | `APP_NAME` | `ML Prediction API` | Display name used in API metadata. |
| `app_version` | `APP_VERSION` | `0.1.0` | Reported in `/` and `/health-ui`. |
| `debug` | `DEBUG` | `true` | Debug flag (set `false` in cluster). |
| `model_path` | `MODEL_PATH` | `./models/yolo11l-cls.onnx` | Path to the ONNX model file. |
| `class_names_path` | `CLASS_NAMES_PATH` | `./models/imagenet_classes.txt` | Path to the newline-delimited class label file. |
| `model_confidence_threshold` | `MODEL_CONFIDENCE_THRESHOLD` | `0.25` | Minimum confidence for a prediction to be included in the response. |
| `max_predictions` | `MAX_PREDICTIONS` | `5` | Maximum number of top predictions returned. |
| `max_upload_size` | `MAX_UPLOAD_SIZE` | `10485760` (10MB) | Max accepted upload size in bytes. |
| `allowed_extensions` | `ALLOWED_EXTENSIONS` | `.jpg,.jpeg,.png,.webp` | Accepted image file extensions. |
| `enable_metrics` | `ENABLE_METRICS` | `true` | Toggles Prometheus metric recording. |

---

## Prerequisites

- **Python 3.11+** (the Docker image builds on `python:3.11-slim`; local development was done against Python 3.13, see `.python-version`)
- **Docker**
- **Minikube** (or another local/remote Kubernetes cluster)
- **kubectl**
- **Helm 3**
- **git** (used by `run.sh` to fetch the VPA CRDs/controller manifests from the `kubernetes/autoscaler` repo)

---

## Running Locally (No Kubernetes)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then visit:
- API docs: http://localhost:8000/docs
- Health dashboard: http://localhost:8000/health-ui
- Metrics: http://localhost:8000/metrics

---

## Running with Docker

```bash
docker build -t ml-api:v1.0 .
docker run --rm -p 8000:8000 ml-api:v1.0
```

The image runs as a non-root user and includes a container-level `HEALTHCHECK` against `/health`.

---

## Running on Kubernetes (Full Stack)

The fastest path is the bundled bootstrap script, which stands up a local Minikube cluster, installs the VPA controller, builds and loads the Docker image, installs the `kube-prometheus-stack` (Prometheus + Grafana), applies the custom Grafana dashboard, deploys the API via Helm, and port-forwards everything:

```bash
./run.sh
```

Once it finishes, it will print:
- **ML API:** http://localhost:8001
- **API Docs:** http://localhost:8001/docs
- **Health UI:** http://localhost:8001/health-ui
- **Grafana:** http://localhost:3000 (credentials printed by the script)

### Manual, step-by-step equivalent

```bash
# 1. Start a local cluster and enable required addons
minikube start --driver=docker --memory=6144 --cpus=4
minikube addons enable ingress
minikube addons enable metrics-server

# 2. Build the image and load it into Minikube
docker build -t ml-api:v1.0 .
minikube image load ml-api:v1.0

# 3. Install the Prometheus + Grafana monitoring stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install monitoring prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
kubectl apply -f k8s/grafana-dashboard.yaml

# 4. Deploy the API via the Helm chart (defaults to HPA mode, values.yaml)
helm upgrade --install ml-api charts/ml-api -n ml-api --create-namespace

# 5. Verify everything is up
kubectl get pods,svc,hpa,ingress -n ml-api

# 6. Port-forward the API and Grafana
kubectl port-forward svc/ml-api 8001:80 -n ml-api &
kubectl port-forward svc/monitoring-grafana 3000:80 -n monitoring &
```

To deploy with an environment-specific overlay instead of the defaults:

```bash
helm upgrade --install ml-api charts/ml-api -n ml-api --create-namespace -f charts/ml-api/values-dev.yaml
# or
helm upgrade --install ml-api charts/ml-api -n ml-api --create-namespace -f charts/ml-api/values-prod.yaml
```

> Note: `k8s/*.yaml` contains equivalent plain Kubernetes manifests (no Helm templating) kept as a reference/fallback for applying resources directly with `kubectl apply -f k8s/`.

---

## Switching Between HPA and VPA

The chart supports two mutually-exclusive autoscaling strategies, controlled by `autoscaling.mode` in `values.yaml`:

```bash
# Horizontal Pod Autoscaler — scale the number of pods
helm upgrade ml-api charts/ml-api -n ml-api --set autoscaling.mode=hpa
kubectl get hpa -n ml-api -w

# Vertical Pod Autoscaler — scale each pod's CPU/memory requests
helm upgrade ml-api charts/ml-api -n ml-api --set autoscaling.mode=vpa
kubectl delete pod -n ml-api -l app.kubernetes.io/name=ml-api   # re-create pods so VPA-assigned resources apply
kubectl get vpa -n ml-api
```

`run.sh` installs the VPA CRDs/controller from the upstream [`kubernetes/autoscaler`](https://github.com/kubernetes/autoscaler) repo automatically the first time it runs, since VPA support is not built into stock Kubernetes/Minikube.

---

## Load Testing / Demonstrating Autoscaling

With the API port-forwarded to `localhost:8001`, generate sustained traffic to trigger the HPA/VPA:

```bash
python app/simulate_traffic.py
```

This continuously posts `images/bus.jpg` to `/predict` once per second (and intentionally sends an invalid file every 20th request to also exercise the error-metrics path). While it runs, watch the autoscaler react:

```bash
kubectl get hpa -n ml-api -w      # replica count climbing with load
kubectl get pods -n ml-api -w     # new pods being scheduled/terminated
```

---

## Monitoring & Dashboards

- **`/metrics`** on every pod exposes:
  - `app_request_count{method, endpoint}` / `app_request_latency_seconds{endpoint}` — generic HTTP traffic metrics (via middleware).
  - `prediction_requests_total{status}` / `prediction_request_latency_seconds` — business-level metrics for the `/predict` endpoint, bucketed for P95/P99 latency calculations.
- A **`ServiceMonitor`** (`charts/ml-api/templates/servicemonitor.yaml`) tells the Prometheus Operator to scrape `/metrics` on the `ml-api` Service every 15s (30s in the `prod` overlay), labeled to be picked up by the `kube-prometheus-stack` release named `monitoring`.
- A custom **Grafana dashboard** is provisioned via `k8s/grafana-dashboard.yaml`, auto-loaded by Grafana's dashboard sidecar.
- Retrieve the generated Grafana admin password:
  ```bash
  kubectl --namespace monitoring get secrets monitoring-grafana \
    -o jsonpath="{.data.admin-password}" | base64 -d; echo
  ```

---

## Testing

The project includes a pytest suite that exercises the FastAPI app directly (no live server required):

```bash
pip install -r requirements.txt
pytest -q
```

Covers:
- `test_health.py` — `/health` reports a healthy, model-loaded status.
- `test_predict.py` — a real image (`images/bus.jpg`) produces a non-empty, well-formed prediction list.
- `test_error_handling.py` — uploading a non-image file returns a structured 4xx error instead of a 500.

---

## Cleanup

Tear down the entire local environment (Helm releases, namespaces, and the Minikube cluster/image):

```bash
./cleanup.sh
```
