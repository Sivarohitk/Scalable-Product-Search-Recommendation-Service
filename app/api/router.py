from fastapi import APIRouter

from app.api.routes.autocomplete import router as autocomplete_router
from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.recommendations import router as recommendations_router
from app.api.routes.search import router as search_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(metrics_router)
api_router.include_router(search_router)
api_router.include_router(autocomplete_router)
api_router.include_router(recommendations_router)
