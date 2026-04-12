"""SSO session and state management."""
from __future__ import annotations

import secrets
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger("monorelay.sso")


class SSOSession:
    """SSO authorization session."""

    def __init__(
        self,
        state: str,
        code_verifier: str,
        redirect_uri: str = "",
        created_at: float = None,
        expires_at: float = None,
    ):
        self.state = state
        self.code_verifier = code_verifier
        self.redirect_uri = redirect_uri
        self.created_at = created_at or datetime.now().timestamp()
        self.expires_at = expires_at or (datetime.now() + timedelta(minutes=10)).timestamp()

    def is_expired(self) -> bool:
        return datetime.now().timestamp() > self.expires_at

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "code_verifier": self.code_verifier,
            "redirect_uri": self.redirect_uri,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class SSOSessionManager:
    """Manages SSO sessions for PKCE flow."""

    def __init__(self):
        self._sessions: dict[str, SSOSession] = {}

    def create_session(self, redirect_uri: str = "") -> SSOSession:
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        session = SSOSession(state=state, code_verifier=code_verifier, redirect_uri=redirect_uri)
        self._sessions[state] = session
        self._cleanup_expired()
        return session

    def get_session(self, state: str) -> Optional[SSOSession]:
        session = self._sessions.get(state)
        if session and not session.is_expired():
            return session
        if state in self._sessions:
            del self._sessions[state]
        return None

    def remove_session(self, state: str) -> None:
        if state in self._sessions:
            del self._sessions[state]

    def _cleanup_expired(self) -> None:
        now = datetime.now().timestamp()
        expired = [s for s in self._sessions.values() if now > s.expires_at]
        for session in expired:
            self._sessions.pop(session.state, None)


class SSOStateManager:
    """Manages SSO state and user sessions."""

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def save_user(self, state: str, user_data: dict, tokens: dict) -> None:
        self._sessions[state] = {
            "user": user_data,
            "tokens": tokens,
            "created_at": datetime.now().timestamp(),
        }

    def get_user(self, state: str) -> Optional[dict]:
        session = self._sessions.get(state)
        if session:
            return {
                "user": session["user"],
                "tokens": session["tokens"],
            }
        return None

    def remove_session(self, state: str) -> None:
        self._sessions.pop(state, None)


sso_session_manager = SSOSessionManager()
sso_state_manager = SSOStateManager()
