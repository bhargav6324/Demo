from dataclasses import dataclass, field

from app.schemas.library import Role


@dataclass(frozen=True)
class UserContext:
    """Authenticated caller. Built by the identity adapter, never by the LLM.
    The raw token is kept out of repr so it cannot leak into logs or prompts."""
    user_id: str
    name: str
    role: Role
    token: str = field(repr=False)

    @property
    def is_librarian(self) -> bool:
        return self.role == "librarian"
