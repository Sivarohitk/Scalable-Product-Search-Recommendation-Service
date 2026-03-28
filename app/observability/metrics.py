from prometheus_client import Counter, Histogram

HTTP_REQUESTS_TOTAL = Counter(
    "product_search_http_requests_total",
    "Total HTTP requests handled by the service.",
    ["method", "path", "status_code"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "product_search_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
HTTP_ERRORS_TOTAL = Counter(
    "product_search_http_errors_total",
    "Total HTTP requests that completed with a 4xx or 5xx status code.",
    ["method", "path", "status_code"],
)
DEPENDENCY_HEALTH_CHECKS_TOTAL = Counter(
    "product_search_dependency_health_checks_total",
    "Total dependency health checks performed by readiness probes.",
    ["dependency", "status"],
)
CACHE_REQUESTS_TOTAL = Counter(
    "product_search_cache_requests_total",
    "Total cache requests by endpoint and outcome.",
    ["endpoint", "outcome"],
)
FALLBACKS_TOTAL = Counter(
    "product_search_fallbacks_total",
    "Total fallback executions by endpoint and fallback path.",
    ["endpoint", "path"],
)


def record_http_request(method: str, path: str, status_code: str, duration_seconds: float) -> None:
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status_code=status_code).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_seconds)
    if status_code.startswith(("4", "5")):
        HTTP_ERRORS_TOTAL.labels(method=method, path=path, status_code=status_code).inc()


def record_dependency_health_check(dependency: str, status: str) -> None:
    DEPENDENCY_HEALTH_CHECKS_TOTAL.labels(dependency=dependency, status=status).inc()


def record_cache_request(endpoint: str, outcome: str) -> None:
    CACHE_REQUESTS_TOTAL.labels(endpoint=endpoint, outcome=outcome).inc()


def record_fallback(endpoint: str, path: str) -> None:
    FALLBACKS_TOTAL.labels(endpoint=endpoint, path=path).inc()
