"""Scoring router — POST /score for ML credit scoring."""

from fastapi import APIRouter

router = APIRouter()


@router.post("/score")
async def score(data: dict):
    """Query the ML service for a credit score prediction.

    Receives tokenized user features, calls MLClient, returns prediction.
    """
    # TODO: validate features → MLClient.predict() → format response
    pass
