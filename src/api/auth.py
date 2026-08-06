from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, FrozenSet

from fastapi import Depends, Header, HTTPException, status


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    username: str
    email: str
    groups: FrozenSet[str]


class CognitoTokenVerifier:
    def __init__(self) -> None:
        self.region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.user_pool_id = os.getenv("COGNITO_USER_POOL_ID", "")
        self.client_id = os.getenv("COGNITO_APP_CLIENT_ID", "")
        if not self.user_pool_id or not self.client_id:
            raise RuntimeError("Thiếu COGNITO_USER_POOL_ID hoặc COGNITO_APP_CLIENT_ID")

        import jwt

        self.jwt = jwt
        self.issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{self.user_pool_id}"
        self.keys = jwt.PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True)

    def verify(self, token: str) -> CurrentUser:
        signing_key = self.keys.get_signing_key_from_jwt(token)
        claims = self.jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=self.issuer,
            options={"verify_aud": False},
        )
        token_use = claims.get("token_use")
        if token_use == "id" and claims.get("aud") != self.client_id:
            raise ValueError("Token audience không hợp lệ")
        if token_use == "access" and claims.get("client_id") != self.client_id:
            raise ValueError("Token client_id không hợp lệ")
        if token_use not in {"id", "access"}:
            raise ValueError("Token type không hợp lệ")

        return CurrentUser(
            user_id=str(claims.get("sub", "")),
            username=str(claims.get("cognito:username") or claims.get("username") or ""),
            email=str(claims.get("email", "")),
            groups=frozenset(claims.get("cognito:groups", [])),
        )


@lru_cache(maxsize=1)
def _verifier() -> CognitoTokenVerifier:
    return CognitoTokenVerifier()


async def current_user(authorization: str = Header(default="")) -> CurrentUser:
    if os.getenv("AUTH_DISABLED", "0").lower() in {"1", "true", "yes", "y"}:
        return CurrentUser(
            user_id="local-development-user",
            username="local-admin",
            email="",
            groups=frozenset({"admins", "editors", "users"}),
        )

    if not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Thiếu Bearer token",
        )
    try:
        return _verifier().verify(authorization.split(" ", 1)[1].strip())
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn",
        ) from exc


def require_roles(*roles: str) -> Callable:
    allowed = frozenset(roles)

    async def dependency(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if not user.groups.intersection(allowed):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện thao tác này",
            )
        return user

    return dependency
