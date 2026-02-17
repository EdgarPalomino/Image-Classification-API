import io
import logging
import os
import time
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse, Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from app.config import get_settings
from app.litemodel import model_predictor
from app.schemas import PredictionResponse, HealthResponse, ErrorResponse

# ---------------- Logging configuration ----------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------- App settings & initialization ----------------

settings = get_settings()

app = FastAPI(
    title="ML Image Classification API",
    version=settings.app_version,
    description="Auto-scaling ML prediction API using YOLO11l",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Static files (for custom Swagger CSS, favicon, etc.)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates (for health-ui)
templates = Jinja2Templates(directory="app/templates")

# Application start time (used for uptime display)
START_TIME = time.time()

# ---------------- Prometheus metrics ----------------

# Generic request-level metrics (per HTTP method + path)
REQUEST_COUNT = Counter(
    "app_request_count",
    "Total number of API requests",
    ["method", "endpoint"],
)

REQUEST_LATENCY = Histogram(
    "app_request_latency_seconds",
    "API request latency in seconds",
    ["endpoint"],
)

# Business-level metrics for /predict:
# Total prediction requests by status (success / error)
PREDICTION_REQUESTS_TOTAL = Counter(
    "prediction_requests_total",
    "Total number of prediction requests by status",
    ["status"],  # status = success / error
)

# Prediction latency histogram (used to compute P95, P99, etc.)
PREDICTION_REQUEST_LATENCY = Histogram(
    "prediction_request_latency_seconds",
    "Prediction request end-to-end latency in seconds",
    buckets=(0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0),
)

# ---------------- Startup event ----------------

@app.on_event("startup")
async def startup_event():
    """
    Initialize model on application startup.

    This ensures the model is loaded and ready before serving traffic.
    """
    logger.info("Starting application...")
    try:
        # This will load the model if not already loaded; if loading fails,
        # we fail fast instead of serving half-broken predictions.
        if not model_predictor.is_loaded():
            raise RuntimeError("Failed to load model during startup")
        logger.info("Application started successfully")
    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise


# ---------------- Basic endpoints ----------------

@app.get("/", tags=["General"])
async def root():
    """
    Root endpoint that provides basic API information.
    """
    return {
        "message": "ML Prediction API",
        "version": settings.app_version,
        "endpoints": {
            "health": "/health",
            "health_ui": "/health-ui",
            "predict": "/predict",
            "metrics": "/metrics",
            "metrics_ui": "/metrics-ui",
            "docs": "/docs",
        },
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """
    Health check endpoint for Kubernetes liveness/readiness probes.

    Returns 200 with status='healthy' if the model is loaded,
    otherwise returns 503 with status='unhealthy'.
    """
    uptime = time.time() - START_TIME
    is_healthy = model_predictor.is_loaded()

    response = HealthResponse(
        status="healthy" if is_healthy else "unhealthy",
        model_loaded=is_healthy,
        model_path=settings.model_path,
        uptime_seconds=round(uptime, 2),
    )

    if not is_healthy:
        # Kubernetes can use this to mark the pod as not ready.
        return JSONResponse(
            status_code=503,
            content=response.model_dump(),
        )

    return response


# ---------------- Prediction endpoint with metrics ----------------

@app.post("/predict", response_model=PredictionResponse, tags=["Prediction"])
async def predict(file: UploadFile = File(...)):
    """
    Predict image class using YOLO11l model.

    - **file**: Image file (jpg, jpeg, png, webp)

    Returns top-5 predictions with confidence scores.
    Also records:
      - prediction_requests_total{status="success"/"error"}
      - prediction_request_latency_seconds (histogram for P95 latency)
    """
    request_start = time.time()

    try:
        # ---- 1. Validate file extension ----
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in settings.allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {settings.allowed_extensions}",
            )

        # ---- 2. Read and validate file size ----
        contents = await file.read()
        if len(contents) > settings.max_upload_size:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"File too large. Max size: "
                    f"{settings.max_upload_size / 1024 / 1024}MB"
                ),
            )

        # ---- 3. Load image and normalize format ----
        try:
            image = Image.open(io.BytesIO(contents))
            # Convert to RGB if necessary (handles RGBA, grayscale, etc.)
            if image.mode != "RGB":
                image = image.convert("RGB")
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid image file: {str(e)}",
            )

        # ---- 4. Run model prediction ----
        predictions, inference_time = model_predictor.predict(image)

        # ---- 5. Build response ----
        response = PredictionResponse(
            success=True,
            predictions=predictions,
            model_version="yolo11l-cls",
            inference_time_ms=round(inference_time, 2),
        )

        logger.info(
            f"Prediction successful: {len(predictions)} results "
            f"in {inference_time:.2f}ms"
        )

        # ---- 6. Record success metrics ----
        elapsed = time.time() - request_start
        if settings.enable_metrics:
            PREDICTION_REQUEST_LATENCY.observe(elapsed)
            PREDICTION_REQUESTS_TOTAL.labels(status="success").inc()

        return response

    except HTTPException as http_exc:
        # Record business-level error metrics for known HTTP errors.
        elapsed = time.time() - request_start
        if settings.enable_metrics:
            PREDICTION_REQUEST_LATENCY.observe(elapsed)
            PREDICTION_REQUESTS_TOTAL.labels(status="error").inc()
        raise http_exc

    except Exception as e:
        # Catch-all for unexpected errors; still record latency + error count.
        elapsed = time.time() - request_start
        if settings.enable_metrics:
            PREDICTION_REQUEST_LATENCY.observe(elapsed)
            PREDICTION_REQUESTS_TOTAL.labels(status="error").inc()

        logger.error(f"Prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- Middleware for generic HTTP metrics ----------------

@app.middleware("http")
async def track_requests(request: Request, call_next):
    """
    Middleware to track all HTTP requests.

    Records per-endpoint request count and latency for generic monitoring.
    """
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time

    # Expose processing time in response headers for debugging.
    response.headers["X-Process-Time"] = str(process_time)

    # Update Prometheus metrics if enabled.
    if settings.enable_metrics:
        REQUEST_COUNT.labels(request.method, request.url.path).inc()
        REQUEST_LATENCY.labels(request.url.path).observe(process_time)

    return response


# ---------------- Metrics endpoint ----------------

@app.get("/metrics")
def metrics():
    """
    Expose Prometheus metrics endpoint.

    This is scraped by Prometheus via ServiceMonitor.
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------------- Pretty health UI ----------------

@app.get("/health-ui", response_class=HTMLResponse)
async def health_ui(request: Request):
    """
    Human-friendly health dashboard page.

    This does not affect Kubernetes probes; it is only for manual inspection.
    """
    uptime_seconds = int(time.time() - START_TIME)
    hours, remainder = divmod(uptime_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    uptime_str = f"{hours}h {minutes}m {seconds}s"

    return templates.TemplateResponse(
        "health.html",
        {
            "request": request,
            "status": "healthy",
            "app_name": "ML Prediction API",
            "version": os.getenv("APP_VERSION", settings.app_version),
            "uptime": uptime_str,
            "model_loaded": "Yes" if model_predictor.is_loaded() else "No",
            "environment": os.getenv("ENVIRONMENT", "local"),
            "now": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    )

@app.get("/metrics-ui", response_class=HTMLResponse, tags=["General"])
async def metrics_ui(request: Request):
    """
    Human-friendly metrics overview page.

    This does NOT replace /metrics. Prometheus still scrapes /metrics in
    plain text format. This page is only for documentation and manual inspection.
    """
    return templates.TemplateResponse(
        "metrics.html",
        {
            "request": request,
        },
    )


# ---------------- Error handlers ----------------

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """
    Custom 404 handler to return a structured error response.
    """
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            error="Not Found",
            detail=f"The path {request.url.path} does not exist",
        ).model_dump(),
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    """
    Custom 500 handler to avoid leaking internal stack traces to clients.
    """
    logger.error(f"Internal error: {exc}")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal Server Error",
            detail="An unexpected error occurred",
        ).model_dump(),
    )