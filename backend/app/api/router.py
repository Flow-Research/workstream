"""Top-level API router composition."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.auth import actors_router, router as auth_router
from app.api.routes.health import router as health_router
from app.modules.checkers.router import router as checkers_router
from app.api.routes.artifact_submissions import router as artifact_submission_router
from app.modules.artifacts.router import router as artifacts_router
from app.modules.authorization.router import router as authorization_router
from app.modules.projects.router import router as projects_router
from app.modules.projects.create_router import router as project_create_router
from app.modules.projects.guide_mutation_router import router as guide_mutation_router
from app.modules.projects.policy_mutation_router import router as policy_mutation_router
from app.modules.tasks.router import router as tasks_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(health_router, prefix="/api/v1")
api_router.include_router(auth_router, prefix="/api/v1")
api_router.include_router(actors_router, prefix="/api/v1")
api_router.include_router(authorization_router, prefix="/api/v1")
api_router.include_router(project_create_router, prefix="/api/v1")
api_router.include_router(guide_mutation_router, prefix="/api/v1")
api_router.include_router(policy_mutation_router, prefix="/api/v1")
api_router.include_router(projects_router, prefix="/api/v1")
api_router.include_router(tasks_router, prefix="/api/v1")
api_router.include_router(checkers_router, prefix="/api/v1")
api_router.include_router(artifacts_router, prefix="/api/v1")
api_router.include_router(artifact_submission_router, prefix="/api/v1")
