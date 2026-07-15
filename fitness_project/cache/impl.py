"""Small in-process plan cache used when Redis is unavailable."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

from fitness_project.config.settings import settings


class PlanCache:
    def __init__(self) -> None:
        self._items: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}

    @staticmethod
    def _key(user_input: str, user_profile: dict, user_id: int) -> str:
        value = json.dumps(
            [user_id, user_input, user_profile],
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def get_cached_plan(
        self,
        user_input: str,
        user_profile: dict,
        user_id: int,
    ) -> Optional[Dict[str, Any]]:
        key = self._key(user_input, user_profile, user_id)
        item = self._items.get(key)
        if not item:
            return None
        created_at, plan = item
        if datetime.now(timezone.utc) - created_at > timedelta(
            hours=settings.CACHE_EXPIRE_HOURS
        ):
            self._items.pop(key, None)
            return None
        return plan

    def set_cached_plan(
        self,
        user_input: str,
        user_profile: dict,
        plan: Dict[str, Any],
        user_id: int,
    ) -> None:
        self._items[self._key(user_input, user_profile, user_id)] = (
            datetime.now(timezone.utc),
            plan,
        )
