from app.schemas.library import AccessLevel, Role


def can_access(role: Role | None, access_level: AccessLevel) -> bool:
    """Whether a caller may read a resource's *content* (backend rule).
    Catalog metadata is always visible; this gates full text, excerpts and RAG chunks."""
    if access_level == "public":
        return True
    if role is None:
        return False
    if access_level == "authenticated":
        return True
    return role == "librarian"  # restricted: librarian only in this prototype
