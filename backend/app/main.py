from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routers import approvals, auth, cases, files, organizations


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth.router)
    app.include_router(organizations.router)
    app.include_router(cases.router)
    app.include_router(approvals.router)
    app.include_router(files.router)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok", "environment": settings.environment, "llm_enabled": settings.llm_enabled,
                "agent_run_mode": settings.agent_run_mode}

    return app


app = create_app()
