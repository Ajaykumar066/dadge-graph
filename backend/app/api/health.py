"""
health.py

Keep-alive endpoint + wake-up status.
Render free tier sleeps after 15 min inactivity.
We ping this endpoint every 14 minutes to prevent sleep.
"""

from fastapi import APIRouter
from app.core.database import get_driver

router = APIRouter(tags=["System"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "SAP O2C Graph API"}


@router.get("/ping")
async def ping():
    """
    Lightweight ping — just confirms the server is awake.
    Used by the frontend keep-alive mechanism.
    """
    return {"alive": True}


@router.get("/wake")
async def wake():
    """
    Full wake-up check — verifies Neo4j is also connected.
    Called by frontend on initial load.
    """
    try:
        driver = get_driver()
        with driver.session() as session:
            session.run("RETURN 1")
        return {"status": "ready", "neo4j": "connected"}
    except Exception as e:
        return {"status": "starting", "neo4j": str(e)}