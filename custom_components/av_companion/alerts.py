"""Device diagnostics and alert history."""

from datetime import datetime, timezone
from typing import Any, Callable
import logging

_LOGGER = logging.getLogger(__name__)


class LGDisplayAlertState:
    """Store alert and diagnostic events for notification automations."""

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._active_issues: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []
        self._listeners: set[Callable[[], None]] = set()
        self._last_event: dict[str, Any] = {
            "code": "ok",
            "message": "OK",
            "level": "info",
            "source": None,
            "trigger": None,
            "details": {},
            "updated_at": self._timestamp(),
        }

    def _timestamp(self) -> str:
        """Return an ISO timestamp for state updates."""
        return datetime.now(timezone.utc).isoformat()

    def subscribe(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Subscribe to alert-state changes."""
        self._listeners.add(listener)

        def _unsubscribe() -> None:
            self._listeners.discard(listener)

        return _unsubscribe

    def _notify(self) -> None:
        """Notify all subscribed entities that the alert state changed."""
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.debug("Alert listener callback failed", exc_info=True)

    def _append_history(self, event: dict[str, Any]) -> None:
        """Keep a short rolling history of alert events."""
        self._history.insert(0, event)
        del self._history[10:]

    def set_issue(
        self,
        code: str,
        message: str,
        *,
        level: str = "warning",
        source: str | None = None,
        trigger: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record or update an active issue."""
        issue = {
            "code": code,
            "message": message,
            "level": level,
            "source": source,
            "trigger": trigger,
            "details": details or {},
            "updated_at": self._timestamp(),
        }

        current = self._active_issues.get(code)
        if current is not None:
            comparable_current = dict(current)
            comparable_issue = dict(issue)
            comparable_current.pop("updated_at", None)
            comparable_issue.pop("updated_at", None)
            if comparable_current == comparable_issue:
                return

        self._active_issues[code] = issue
        self._last_event = {**issue, "event": "issue_set"}
        self._append_history(self._last_event)
        self._notify()

    def clear_issue(self, code: str, *, message: str | None = None) -> None:
        """Clear an active issue if it exists."""
        existing = self._active_issues.pop(code, None)
        if existing is None:
            return

        clear_event = {
            "code": code,
            "message": message or f"Resolved: {existing.get('message', code)}",
            "level": "info",
            "source": existing.get("source"),
            "trigger": existing.get("trigger"),
            "details": existing.get("details", {}),
            "updated_at": self._timestamp(),
            "event": "issue_cleared",
        }
        self._last_event = clear_event
        self._append_history(clear_event)
        self._notify()

    @property
    def state(self) -> str:
        """Return the user-visible alert summary."""
        if not self._active_issues:
            return "OK"

        newest_issue = max(
            self._active_issues.values(),
            key=lambda item: str(item.get("updated_at", "")),
        )
        return str(
            newest_issue.get("message") or newest_issue.get("code") or "Issue detected"
        )[:255]

    @property
    def attributes(self) -> dict[str, Any]:
        """Return extended alert details for Home Assistant automations."""
        last_event = self._last_event
        return {
            "entry_id": self._entry_id,
            "level": last_event.get("level", "info"),
            "last_code": last_event.get("code", "ok"),
            "last_message": last_event.get("message", "OK"),
            "last_source": last_event.get("source"),
            "last_trigger": last_event.get("trigger"),
            "updated_at": last_event.get("updated_at"),
            "issue_count": len(self._active_issues),
            "active_issues": list(self._active_issues.values()),
            "history": self._history[:5],
        }
