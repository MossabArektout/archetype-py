"""Business logic layer: the user service orchestrates repository access."""

from app.repositories.users import UserRepository


class UserService:
    def __init__(self) -> None:
        self._repository = UserRepository()

    def get_user(self, user_id: int) -> dict:
        return self._repository.find_by_id(user_id)

    def create_user(self, name: str, email: str) -> dict:
        return self._repository.save({"name": name, "email": email})
