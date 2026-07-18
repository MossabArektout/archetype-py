"""HTTP layer: FastAPI routes for user endpoints."""

from fastapi import APIRouter

from app.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])
_service = UserService()


@router.get("/{user_id}")
def get_user(user_id: int) -> dict:
    return _service.get_user(user_id)


@router.post("/")
def create_user(name: str, email: str) -> dict:
    return _service.create_user(name, email)
