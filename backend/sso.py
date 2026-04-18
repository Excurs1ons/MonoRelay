"""Python-native SSO module using OAuth/OIDC."""
from __future__ import annotations

import logging
import secrets
import hashlib
import base64
from typing import Optional
from urllib.parse import urlencode

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client

logger = logging.getLogger("monorelay.sso")

try:
    from jose import jwt, JWTError
    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False


def _generate_pkce_codes() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode().rstrip('=')
    return code_verifier, code_challenge


class OAuthProvider:
    GITHUB = "github"
    GOOGLE = "google"
    PRISMAAUTH = "prismaauth"


class SSOConfig:
    enabled: bool = False
    provider: str = OAuthProvider.PRISMAAUTH
    prismaauth_url: str = "http://localhost:8080"
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = ["openid", "profile", "email"]
    
    github_client_id: str = ""
    github_client_secret: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    
    @property
    def is_configured(self) -> bool:
        """Check if SSO is properly configured for the current provider."""
        if not self.enabled:
            return False
        
        if self.provider == OAuthProvider.PRISMAAUTH:
            return bool(self.client_id and self.client_secret and self.prismaauth_url)
        elif self.provider == OAuthProvider.GITHUB:
            return bool(self.github_client_id and self.github_client_secret)
        elif self.provider == OAuthProvider.GOOGLE:
            return bool(self.google_client_id and self.google_client_secret)
        
        return False


class SSOUser:
    def __init__(self, provider: str, profile: dict, tokens: dict = None):
        self.provider = provider
        # Ensure provider_id is a string (GitHub returns numeric IDs)
        self.provider_id = str(profile.get("id") or profile.get("sub", ""))
        self.username = profile.get("username") or profile.get("login") or profile.get("name", "") or profile.get("email", "").split("@")[0]
        self.email = profile.get("email", "")
        self.name = profile.get("name", "") or profile.get("login", "")
        self.avatar_url = profile.get("picture") or profile.get("avatar_url", "")
        self.is_admin = profile.get("is_admin", False)
        self.roles = profile.get("roles", [])
        self.raw_profile = profile
        self.tokens = tokens or {}
    
    @property
    def unique_id(self) -> str:
        return f"{self.provider}:{self.provider_id}"
    
    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "provider_id": self.provider_id,
            "username": self.username,
            "email": self.email,
            "name": self.name,
            "avatar_url": self.avatar_url,
        }


class OAuthValidator:
    def __init__(self, config: SSOConfig):
        self.config = config
    
    def get_authorization_url(self, state: str, redirect_uri: str, code_verifier: str = "", code_challenge: str = "") -> str:
        provider = self.config.provider
        
        if provider == OAuthProvider.PRISMAAUTH:
            params = {
                "client_id": self.config.client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "scope": " ".join(self.config.scopes),
            }
            if code_challenge:
                params["code_challenge"] = code_challenge
                params["code_challenge_method"] = "S256"
            base_url = self.config.prismaauth_url.rstrip("/")
            return f"{base_url}/login?{urlencode(params)}"
        
        elif provider == OAuthProvider.GITHUB:
            params = {
                "client_id": self.config.github_client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(self.config.scopes),
                "state": state,
            }
            if code_challenge:
                params["code_challenge"] = code_challenge
                params["code_challenge_method"] = "S256"
            return f"https://github.com/login/oauth/authorize?{urlencode(params)}"
        
        elif provider == OAuthProvider.GOOGLE:
            params = {
                "client_id": self.config.google_client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(self.config.scopes),
                "response_type": "code",
                "state": state,
                "access_type": "online",
            }
            if code_challenge:
                params["code_challenge"] = code_challenge
                params["code_challenge_method"] = "S256"
            return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        
        raise ValueError(f"Unsupported provider: {provider}")
    
    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str = "") -> Optional[dict]:
        provider = self.config.provider
        
        try:
            if provider == OAuthProvider.PRISMAAUTH:
                base_url = self.config.prismaauth_url.rstrip("/")
                token_url = f"{base_url}/token"
                logger.info(f"Exchanging code at {token_url}")
                
                data = {
                    "grant_type": "authorization_code",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                }
                if code_verifier:
                    data["code_verifier"] = code_verifier
                
                async with httpx.AsyncClient() as client:
                    resp = await client.post(token_url, data=data)
                    logger.info(f"Token response status: {resp.status_code}")
                    logger.info(f"Token response body: {resp.text[:500]}")
                    
                    if resp.status_code != 200:
                        logger.error(f"Token exchange failed: {resp.text}")
                        return None
                        
                    return resp.json()
            
            elif provider == OAuthProvider.GITHUB:
                data = {
                    "client_id": self.config.github_client_id,
                    "client_secret": self.config.github_client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                }
                # GitHub OAuth standard doesn't use PKCE, sending code_verifier might cause issues with some implementations
                # although standard says unknown params should be ignored.
                if code_verifier and provider != OAuthProvider.GITHUB:
                    data["code_verifier"] = code_verifier
                    
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "https://github.com/login/oauth/access_token",
                        data=data,
                        headers={"Accept": "application/json"},
                        timeout=15.0
                    )
                    logger.info(f"GitHub token response: status={resp.status_code}, body={resp.text[:500]}")
                    
                    if resp.status_code != 200:
                        logger.error(f"GitHub token exchange failed: {resp.text}")
                        return None
                        
                    res_json = resp.json()
                    if "error" in res_json:
                        logger.error(f"GitHub returned error: {res_json.get('error')} - {res_json.get('error_description')}")
                        return None
                        
                    return res_json
            
            elif provider == OAuthProvider.GOOGLE:
                data = {
                    "client_id": self.config.google_client_id,
                    "client_secret": self.config.google_client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                }
                if code_verifier:
                    data["code_verifier"] = code_verifier
                resp = await AsyncOAuth2Client().post(
                    "https://oauth2.googleapis.com/token",
                    data=data,
                )
                resp.raise_for_status()
                return resp.json()
            
        except Exception as e:
            logger.error(f"Token exchange failed: {e}")
            return None
        
        return None
    
    async def get_user_info(self, access_token: str) -> Optional[SSOUser]:
        provider = self.config.provider
        
        try:
            headers = {"Authorization": f"Bearer {access_token}"}
            
            if provider == OAuthProvider.PRISMAAUTH:
                base_url = self.config.prismaauth_url.rstrip("/")
                async with httpx.AsyncClient() as client:
                    resp = await client.get(f"{base_url}/userinfo", headers=headers)
                    resp.raise_for_status()
                    profile = resp.json()
                    return SSOUser(provider, profile)
            
            elif provider == OAuthProvider.GITHUB:
                async with httpx.AsyncClient() as client:
                    resp = await client.get("https://api.github.com/user", headers=headers)
                    resp.raise_for_status()
                    profile = resp.json()
                    
                    email_resp = await client.get("https://api.github.com/user/emails", headers=headers)
                    if email_resp.status_code == 200:
                        emails = email_resp.json()
                        for e in emails:
                            if e.get("primary") and e.get("verified"):
                                profile["email"] = e.get("email")
                                break
                
                profile["email"] = profile.get("email") or f"{profile.get('login')}@github.local"
                return SSOUser(provider, profile)
            
            elif provider == OAuthProvider.GOOGLE:
                resp = await AsyncOAuth2Client().get("https://www.googleapis.com/oauth2/v2/userinfo", headers=headers)
                resp.raise_for_status()
                profile = resp.json()
                return SSOUser(provider, profile)
            
        except Exception as e:
            logger.error(f"Failed to get user info: {e}")
            return None
        
        return None


def create_sso_config_from_dict(data: dict) -> SSOConfig:
    config = SSOConfig()
    config.enabled = data.get("enabled", False)
    config.provider = data.get("provider", "prismaauth")
    config.prismaauth_url = data.get("prismaauth_url", "http://localhost:8080")
    config.client_id = data.get("client_id", "")
    config.client_secret = data.get("client_secret", "")
    config.scopes = data.get("scopes", ["openid", "profile", "email"])
    config.github_client_id = data.get("github_client_id", "")
    config.github_client_secret = data.get("github_client_secret", "")
    config.google_client_id = data.get("google_client_id", "")
    config.google_client_secret = data.get("google_client_secret", "")
    return config
