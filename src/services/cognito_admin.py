from __future__ import annotations

import os
from typing import Any, Dict, List

import boto3


class CognitoAdminService:
    def __init__(self) -> None:
        self.user_pool_id = os.getenv("COGNITO_USER_POOL_ID", "")
        if not self.user_pool_id:
            raise RuntimeError("COGNITO_USER_POOL_ID chưa được cấu hình")
        self.client = boto3.client("cognito-idp")

    @staticmethod
    def _normalize_user(user: Dict[str, Any]) -> Dict[str, Any]:
        attributes = {a["Name"]: a["Value"] for a in user.get("Attributes", [])}
        return {
            "username": user.get("Username"),
            "enabled": user.get("Enabled"),
            "status": user.get("UserStatus"),
            "created_at": str(user.get("UserCreateDate", "")),
            "updated_at": str(user.get("UserLastModifiedDate", "")),
            "attributes": attributes,
        }

    def list_users(self, limit: int = 50) -> List[Dict[str, Any]]:
        response = self.client.list_users(
            UserPoolId=self.user_pool_id,
            Limit=max(1, min(limit, 60)),
        )
        return [self._normalize_user(user) for user in response.get("Users", [])]

    def disable_user(self, username: str) -> None:
        self.client.admin_disable_user(UserPoolId=self.user_pool_id, Username=username)

    def enable_user(self, username: str) -> None:
        self.client.admin_enable_user(UserPoolId=self.user_pool_id, Username=username)

    def add_user_to_group(self, username: str, group: str) -> None:
        self.client.admin_add_user_to_group(
            UserPoolId=self.user_pool_id,
            Username=username,
            GroupName=group,
        )
