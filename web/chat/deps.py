"""The chat API router, shared by the route modules and the engine so every
chat endpoint hangs off one APIRouter with the sign-in dependency.
"""

from fastapi import APIRouter, Depends

from web.users import require_user

router = APIRouter(prefix="/api/chat", dependencies=[Depends(require_user)])
