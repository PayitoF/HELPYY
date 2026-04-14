"""Observability router — metrics, health, contract status, cost report."""

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from backend.observability.metrics import get_metrics, get_prometheus
from backend.observability.ml_health import get_ml_status
from backend.observability.business_metrics import get_business_metrics
from backend.observability.contract_monitor import get_contract_status
from backend.observability.cost_tracker import get_cost_report

router = APIRouter()


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    return get_prometheus()


@router.get("/metrics/json")
async def metrics_json():
    return get_metrics()


@router.get("/ml-health")
async def ml_health():
    return get_ml_status()


@router.get("/business-metrics")
async def business_metrics():
    return get_business_metrics()


@router.get("/contract-status")
async def contract_status():
    return get_contract_status()


@router.get("/cost-report")
async def cost_report(days: int = 7):
    return get_cost_report(days)
