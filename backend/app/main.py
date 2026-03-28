# from contextlib import asynccontextmanager
# import logging

# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware

# from app.core.database import get_driver, close_driver
# from app.core.config import get_settings

# from app.api.graph import router as graph_router
# from app.api.chat  import router as chat_router
# from app.api.analytics import router as analytics_router

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
#     datefmt="%H:%M:%S",
# )
# logger = logging.getLogger(__name__)


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     logger.info("Starting SAP O2C Graph API...")
#     get_driver()
#     logger.info("Neo4j connected — API is ready")
#     yield
#     logger.info("Shutting down — closing Neo4j driver...")
#     close_driver()
#     logger.info("Shutdown complete")


# def create_app() -> FastAPI:
#     app = FastAPI(
#         title="SAP O2C Graph API",
#         description="Graph-based query system for SAP Order-to-Cash data",
#         version="1.0.0",
#         lifespan=lifespan,
#     )

#     app.add_middleware(
#         CORSMiddleware,
#         allow_origins=[
#             "http://localhost:5173",
#             "http://localhost:3000",
#             "*",
#         ],
#         allow_credentials=True,
#         allow_methods=["*"],
#         allow_headers=["*"],
#     )

#     @app.get("/health", tags=["System"])
#     async def health():
#         return {"status": "ok", "service": "SAP O2C Graph API"}
#     app.include_router(graph_router)
#     app.include_router(chat_router)
#      app.include_router(analytics_router)
#     return app


# app = create_app()

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import get_driver, close_driver
from app.api.graph     import router as graph_router
from app.api.chat      import router as chat_router
from app.api.analytics import router as analytics_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting SAP O2C Graph API...")
    get_driver()
    logger.info("Neo4j connected — API is ready")
    yield
    logger.info("Shutting down — closing Neo4j driver...")
    close_driver()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SAP O2C Graph API",
        description="Graph-based query system for SAP Order-to-Cash data",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["System"])
    async def health():
        return {"status": "ok", "service": "SAP O2C Graph API"}

    app.include_router(graph_router)
    app.include_router(chat_router)
    app.include_router(analytics_router)

    return app


app = create_app()


