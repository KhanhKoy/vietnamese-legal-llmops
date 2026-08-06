from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    conversation_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class ChatResponse(BaseModel):
    conversation_id: str
    answer: str
    results: List[Dict[str, Any]] = Field(default_factory=list)
    latency_ms: Optional[float] = None
    timings_ms: Dict[str, Any] = Field(default_factory=dict)


class DocumentUploadRequest(BaseModel):
    filename: str
    title: str = Field(min_length=1, max_length=500)
    so_ky_hieu: str = Field(default="", max_length=200)
    loai_van_ban: str = Field(default="", max_length=200)
    co_quan_ban_hanh: str = Field(default="", max_length=300)
    tinh_trang_hieu_luc: str = Field(default="Còn hiệu lực", max_length=100)
    is_procedural_law: bool = False


class DocumentUpdateRequest(BaseModel):
    tinh_trang_hieu_luc: Optional[str] = Field(default=None, max_length=100)
    ngay_het_hieu_luc: Optional[str] = Field(default=None, max_length=30)
    is_procedural_law: Optional[bool] = None


class UserGroupRequest(BaseModel):
    group: str = Field(pattern="^(users|editors|admins)$")
