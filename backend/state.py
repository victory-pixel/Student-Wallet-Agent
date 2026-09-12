
#Tracks which user is currently active in this running session.

_current_user_id: int | None = None


def set_current_user(user_id: int) -> None:
    global _current_user_id
    _current_user_id = user_id


def get_current_user() -> int | None:
    return _current_user_id