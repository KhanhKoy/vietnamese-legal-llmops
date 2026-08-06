from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Query, status

from rag_core.qa_service import QAService
from services.chat_history import ChatHistoryStore
from services.cognito_admin import CognitoAdminService
from services.document_admin import DocumentAdminStore
from services.ingestion import IngestionService

from .auth import CurrentUser, current_user, require_roles
from .schemas import (
    ChatRequest,
    ChatResponse,
    DocumentUpdateRequest,
    DocumentUploadRequest,
    UserGroupRequest,
)

router = APIRouter(prefix="/api")


@lru_cache(maxsize=1)
def qa_service() -> QAService:
    return QAService()


@lru_cache(maxsize=1)
def history_store() -> ChatHistoryStore | None:
    if os.getenv("ENABLE_CHAT_HISTORY", "false").lower() != "true":
        return None
    return ChatHistoryStore()


def required_history_store() -> ChatHistoryStore:
    store = history_store()
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Lưu lịch sử chat chưa được bật",
        )
    return store


@lru_cache(maxsize=1)
def cognito_admin() -> CognitoAdminService:
    return CognitoAdminService()


@lru_cache(maxsize=1)
def ingestion_service() -> IngestionService:
    return IngestionService()


@lru_cache(maxsize=1)
def document_admin() -> DocumentAdminStore:
    return DocumentAdminStore()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: CurrentUser = Depends(current_user)) -> ChatResponse:
    store = history_store()
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    if store is not None and not payload.conversation_id:
        conversation_id = await asyncio.to_thread(
            store.create_conversation, user.user_id, payload.question[:120]
        )

    if store is not None:
        try:
            await asyncio.to_thread(
                store.append_message,
                conversation_id,
                user.user_id,
                "user",
                payload.question,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện") from exc
    response = await qa_service().ask(question=payload.question, top_k=payload.top_k)
    answer = str(response.get("answer", ""))
    results = response.get("results", []) or []
    sources = [str(item.get("chunk_id", "")) for item in results if item.get("chunk_id")]
    if store is not None:
        await asyncio.to_thread(
            store.append_message,
            conversation_id,
            user.user_id,
            "assistant",
            answer,
            sources,
            response.get("latency_ms"),
        )
    return ChatResponse(
        conversation_id=conversation_id,
        answer=answer,
        results=results,
        latency_ms=response.get("latency_ms"),
        timings_ms=response.get("timings_ms", {}) or {},
    )


@router.get("/conversations")
async def conversations(
    limit: int = Query(default=30, ge=1, le=100),
    user: CurrentUser = Depends(current_user),
):
    return await asyncio.to_thread(
        required_history_store().list_conversations, user.user_id, limit
    )


@router.get("/conversations/{conversation_id}")
async def conversation_messages(
    conversation_id: str,
    user: CurrentUser = Depends(current_user),
):
    items = await asyncio.to_thread(
        required_history_store().get_messages, conversation_id, user.user_id
    )
    if not items:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")
    return items


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    user: CurrentUser = Depends(current_user),
):
    deleted = await asyncio.to_thread(
        required_history_store().delete_conversation, conversation_id, user.user_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy cuộc trò chuyện")


@router.get("/admin/conversations")
async def admin_conversations(
    day: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    _: CurrentUser = Depends(require_roles("admins")),
):
    selected_day = day or datetime.now(timezone.utc).date().isoformat()
    return await asyncio.to_thread(
        required_history_store().list_conversations_for_admin, selected_day, limit
    )


@router.get("/admin/users")
async def admin_users(
    limit: int = Query(default=50, ge=1, le=60),
    _: CurrentUser = Depends(require_roles("admins")),
):
    return await asyncio.to_thread(cognito_admin().list_users, limit)


@router.post("/admin/users/{username}/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_user(username: str, _: CurrentUser = Depends(require_roles("admins"))):
    await asyncio.to_thread(cognito_admin().disable_user, username)


@router.post("/admin/users/{username}/enable", status_code=status.HTTP_204_NO_CONTENT)
async def enable_user(username: str, _: CurrentUser = Depends(require_roles("admins"))):
    await asyncio.to_thread(cognito_admin().enable_user, username)


@router.post("/admin/users/{username}/group", status_code=status.HTTP_204_NO_CONTENT)
async def add_user_group(
    username: str,
    payload: UserGroupRequest,
    _: CurrentUser = Depends(require_roles("admins")),
):
    await asyncio.to_thread(cognito_admin().add_user_to_group, username, payload.group)


@router.post("/admin/documents/upload-url")
async def document_upload_url(
    payload: DocumentUploadRequest,
    user: CurrentUser = Depends(require_roles("admins", "editors")),
):
    dump = payload.model_dump if hasattr(payload, "model_dump") else payload.dict
    metadata = dump(exclude={"filename"})
    try:
        return await asyncio.to_thread(
            ingestion_service().create_upload,
            payload.filename,
            metadata,
            user.user_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admin/documents")
async def documents(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: CurrentUser = Depends(require_roles("admins", "editors")),
):
    return await asyncio.to_thread(document_admin().list_documents, limit, offset)


@router.patch("/admin/documents/{document_id}")
async def update_document(
    document_id: str,
    payload: DocumentUpdateRequest,
    _: CurrentUser = Depends(require_roles("admins", "editors")),
):
    updated = await asyncio.to_thread(
        document_admin().update_document_info,
        document_id,
        payload.tinh_trang_hieu_luc,
        payload.ngay_het_hieu_luc,
        payload.is_procedural_law,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản hoặc không có thay đổi")
    return {"updated": True}


@router.delete("/admin/documents/{document_id}")
async def delete_document(
    document_id: str,
    _: CurrentUser = Depends(require_roles("admins")),
):
    deleted = await asyncio.to_thread(document_admin().delete_document, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Không tìm thấy văn bản")
    return {"deleted": True, "mode": "soft-delete"}
