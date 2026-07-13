from __future__ import annotations

import os
from typing import Optional
from google import genai
from google.genai import types
from .config import get_settings


class GeneratorService:
    def __init__(
        self,
        model_name: Optional[str] = None,
        max_new_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> None:
        self.settings = get_settings()

        self.model_name = model_name or os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        self.api_key = os.getenv("GEMINI_API_KEY", "")

        if not self.api_key:
            raise ValueError("❌ Không tìm thấy GEMINI_API_KEY trong file .env.")

        self.client = genai.Client(api_key=self.api_key)

        self.generation_config = types.GenerateContentConfig(
            max_output_tokens=max_new_tokens,
            temperature=temperature,
        )

    def generate(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self.generation_config,
            )
            if response.text:
                return response.text.strip()
            return "⚠️ Gemini không thể sinh câu trả lời do vi phạm chính sách nội dung."
        except Exception as e:
            return f"❌ Lỗi kết nối Gemini API: {str(e)}"