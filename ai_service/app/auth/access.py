from app.schemas.library import AccessLevel, Role

_RESTRICTED_ROLES = {"faculty", "researcher", "librarian"}


def can_access(role: Role | None, access_level: AccessLevel) -> bool:
    """Whether a caller may read a resource's *content*. Catalog metadata is
    always visible; this gates full text, excerpts and RAG chunks."""
    if access_level == "public":
        return True
    if role is None:
        return False
    if access_level == "university":
        return True
    return role in _RESTRICTED_ROLES
