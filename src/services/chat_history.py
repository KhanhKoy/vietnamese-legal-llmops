from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatHistoryStore:
    """DynamoDB repository using one item per message.

    Required table keys: ``pk`` (partition key) and ``sk`` (sort key).
    The infrastructure template also creates user/time indexes used below.
    """

    def __init__(self, table_name: Optional[str] = None) -> None:
        self.table_name = table_name or os.getenv(
            "DYNAMODB_CHAT_TABLE", "LegalChatbotHistory"
        )
        self.user_index = os.getenv("DYNAMODB_USER_INDEX", "gsi_user_updated")
        self.admin_index = os.getenv("DYNAMODB_ADMIN_INDEX", "gsi_admin_date")
        self.ttl_days = int(os.getenv("CHAT_HISTORY_TTL_DAYS", "180"))
        self.table = boto3.resource("dynamodb").Table(self.table_name)

    def create_conversation(self, user_id: str, title: str = "Cuộc trò chuyện mới") -> str:
        conversation_id = str(uuid.uuid4())
        now = _utc_now()
        day = now[:10]
        self.table.put_item(
            Item={
                "pk": f"CONVERSATION#{conversation_id}",
                "sk": "META",
                "entity_type": "conversation",
                "conversation_id": conversation_id,
                "user_id": user_id,
                "title": title[:200],
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
                "expires_at": int(time.time()) + self.ttl_days * 86400,
                "gsi1pk": f"USER#{user_id}",
                "gsi1sk": f"{now}#{conversation_id}",
                "gsi2pk": f"DAY#{day}",
                "gsi2sk": f"{now}#{conversation_id}",
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
        return conversation_id

    def append_message(
        self,
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        sources: Optional[List[str]] = None,
        latency_ms: Optional[float] = None,
    ) -> str:
        meta = self.table.get_item(
            Key={"pk": f"CONVERSATION#{conversation_id}", "sk": "META"},
            ConsistentRead=True,
        ).get("Item")
        if not meta or meta.get("user_id") != user_id:
            raise PermissionError("Conversation không tồn tại hoặc không thuộc user")

        message_id = str(uuid.uuid4())
        now = _utc_now()
        item: Dict[str, Any] = {
            "pk": f"CONVERSATION#{conversation_id}",
            "sk": f"MESSAGE#{now}#{message_id}",
            "entity_type": "message",
            "message_id": message_id,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": now,
            "expires_at": int(time.time()) + self.ttl_days * 86400,
        }
        if sources:
            item["sources"] = sources
        if latency_ms is not None:
            item["latency_ms"] = str(latency_ms)

        self.table.put_item(Item=item)
        self.table.update_item(
            Key={"pk": f"CONVERSATION#{conversation_id}", "sk": "META"},
            UpdateExpression=(
                "SET updated_at = :now, gsi1sk = :gsi1, gsi2pk = :gsi2pk, "
                "gsi2sk = :gsi2sk, expires_at = :expires ADD message_count :one"
            ),
            ConditionExpression="user_id = :uid",
            ExpressionAttributeValues={
                ":now": now,
                ":gsi1": f"{now}#{conversation_id}",
                ":gsi2pk": f"DAY#{now[:10]}",
                ":gsi2sk": f"{now}#{conversation_id}",
                ":one": 1,
                ":uid": user_id,
                ":expires": int(time.time()) + self.ttl_days * 86400,
            },
        )
        return message_id

    def list_conversations(self, user_id: str, limit: int = 30) -> List[Dict[str, Any]]:
        response = self.table.query(
            IndexName=self.user_index,
            KeyConditionExpression=Key("gsi1pk").eq(f"USER#{user_id}"),
            ScanIndexForward=False,
            Limit=max(1, min(limit, 100)),
        )
        return response.get("Items", [])

    def list_conversations_for_admin(self, day: str, limit: int = 100) -> List[Dict[str, Any]]:
        response = self.table.query(
            IndexName=self.admin_index,
            KeyConditionExpression=Key("gsi2pk").eq(f"DAY#{day}"),
            ScanIndexForward=False,
            Limit=max(1, min(limit, 200)),
        )
        return response.get("Items", [])

    def get_messages(self, conversation_id: str, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        meta = self.table.get_item(
            Key={"pk": f"CONVERSATION#{conversation_id}", "sk": "META"}
        ).get("Item")
        if not meta or (user_id is not None and meta.get("user_id") != user_id):
            return []
        key_expression = (
            Key("pk").eq(f"CONVERSATION#{conversation_id}")
            & Key("sk").begins_with("MESSAGE#")
        )
        items: List[Dict[str, Any]] = []
        last_key = None
        while True:
            kwargs: Dict[str, Any] = {"KeyConditionExpression": key_expression}
            if last_key:
                kwargs["ExclusiveStartKey"] = last_key
            response = self.table.query(**kwargs)
            items.extend(response.get("Items", []))
            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                return items

    def delete_conversation(self, conversation_id: str, user_id: str) -> bool:
        meta_key = {"pk": f"CONVERSATION#{conversation_id}", "sk": "META"}
        meta = self.table.get_item(Key=meta_key).get("Item")
        if not meta or meta.get("user_id") != user_id:
            return False

        with self.table.batch_writer() as batch:
            last_key = None
            while True:
                kwargs: Dict[str, Any] = {
                    "KeyConditionExpression": Key("pk").eq(
                        f"CONVERSATION#{conversation_id}"
                    ),
                    "ProjectionExpression": "pk, sk",
                }
                if last_key:
                    kwargs["ExclusiveStartKey"] = last_key
                response = self.table.query(**kwargs)
                for item in response.get("Items", []):
                    batch.delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
                last_key = response.get("LastEvaluatedKey")
                if not last_key:
                    break
        return True
