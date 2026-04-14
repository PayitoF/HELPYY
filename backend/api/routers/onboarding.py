"""Onboarding router — activation code endpoints for web→app flow."""

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.api.activation_codes import get_activation_store

router = APIRouter()
logger = logging.getLogger(__name__)


class ActivateRequest(BaseModel):
    code: str


class ActivateResponse(BaseModel):
    valid: bool
    display_name: str | None = None
    account_id: str | None = None
    session_id: str | None = None
    activation_code: str | None = None


@router.post("/activate", response_model=ActivateResponse)
async def activate_with_code(request: ActivateRequest):
    """Validate an activation code from the web widget.

    Returns the user profile and the original session_id so the app
    can load chat history from that session.
    """
    store = get_activation_store()
    record = store.validate(request.code)

    if record is None:
        return ActivateResponse(valid=False)

    store.mark_used(request.code)
    logger.info("[ONBOARDING] Activation successful: code=%s → account=%s", request.code, record.account_id)

    return ActivateResponse(
        valid=True,
        display_name=record.display_name,
        account_id=record.account_id,
        session_id=record.session_id,
        activation_code=record.code,
    )


@router.get("/chat-history/{session_id}")
async def get_chat_history(session_id: str):
    """Retrieve chat history for a session (used after activation code validation).

    Returns the conversation history so the app can show past messages.
    """
    from backend.api.routers.chat import _get_orchestrator

    orchestrator = _get_orchestrator()
    context = orchestrator.get_session_context(session_id)

    if not context or not context.get("history"):
        return {"messages": [], "session_id": session_id}

    # Filter and format history for the frontend
    messages = []
    for turn in context.get("history", []):
        messages.append({
            "role": turn["role"],
            "content": turn["content"],
            "agent": turn.get("agent"),
        })

    return {
        "messages": messages,
        "session_id": session_id,
        "agent": context.get("current_agent"),
    }


# ─── Direct account creation from the widget form ───────────────────────────

class CreateAccountRequest(BaseModel):
    session_id: str
    name: str
    cedula: str
    income: float


class CreateAccountResponse(BaseModel):
    success: bool
    account_id: str | None = None
    activation_code: str | None = None
    display_name: str | None = None
    credit_eligible: bool = False
    error: str | None = None


@router.post("/create-account", response_model=CreateAccountResponse)
async def create_account_from_form(req: CreateAccountRequest):
    """Create account directly from the widget onboarding form.

    Runs credit check, creates account, enables Helpyy Hand, and returns
    the activation code — all without involving the LLM.
    """
    try:
        # 1. Credit check via ML client
        from backend.ml_client.client import MLClient
        from backend.ml_client.schemas import RiskRequest
        ml = MLClient()
        pred_req = RiskRequest(
            declared_income=req.income,
            is_banked=0,
            employment_type="informal",
            age=30,
            city_type="urban",
            total_sessions=0,
            pct_conversion=0.0,
            tx_income_pct=0.0,
            payments_count=0,
            on_time_rate=0.5,
            overdue_rate=0.0,
            avg_decision_score=0.5,
        )
        try:
            pred = await ml.predict(pred_req)
            eligible = pred.eligible
        except Exception:
            # ML mock unavailable — use simple threshold
            eligible = req.income >= 1_200_000

        # 2. Create account (simulated)
        account_id = f"ACC-{uuid.uuid4().hex[:8].upper()}"

        # 3. First name for display
        first_name = req.name.strip().split()[0] if req.name.strip() else "amigo"

        # 4. Generate activation code
        store = get_activation_store()
        code = store.generate(
            session_id=req.session_id,
            account_id=account_id,
            display_name=first_name,
        )

        logger.info(
            "[ONBOARDING] Form account created: account=%s eligible=%s code=%s",
            account_id, eligible, code,
        )

        return CreateAccountResponse(
            success=True,
            account_id=account_id,
            activation_code=code,
            display_name=first_name,
            credit_eligible=eligible,
        )

    except Exception as exc:
        logger.exception("[ONBOARDING] create-account error: %s", exc)
        return CreateAccountResponse(success=False, error="Error interno. Intenta de nuevo.")
