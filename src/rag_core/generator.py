from __future__ import annotations

import os
from typing import Any, Optional

from .config import get_settings
from .config_manager import get_config


class GeneratorService:
    """Generate answers through Gemini (legacy) or Amazon Bedrock."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> None:
        self.settings = get_settings()
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()

        config = get_config()
        self.max_new_tokens = int(
            max_new_tokens
            if max_new_tokens is not None
            else config.get("max_tokens", self.settings.max_tokens)
        )
        self.temperature = float(
            temperature
            if temperature is not None
            else config.get("temperature", self.settings.temperature)
        )

        if self.provider == "bedrock":
            import boto3
            from botocore.config import Config

            self.model_name = model_name or os.getenv("BEDROCK_LLM_MODEL_ID", "")
            if not self.model_name:
                raise ValueError("Thiếu BEDROCK_LLM_MODEL_ID")
            self.client: Any = boto3.client(
                "bedrock-runtime",
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
                config=Config(
                    retries={"max_attempts": 4, "mode": "standard"},
                    connect_timeout=int(os.getenv("AWS_CONNECT_TIMEOUT_SECONDS", "5")),
                    read_timeout=int(os.getenv("AWS_READ_TIMEOUT_SECONDS", "45")),
                ),
            )
            return

        if self.provider != "gemini":
            raise ValueError("LLM_PROVIDER phải là 'gemini' hoặc 'bedrock'")

        from google import genai
        from google.genai import types

        self.model_name = (
            model_name
            or config.get("model_name")
            or os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        )
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("❌ Không tìm thấy GEMINI_API_KEY trong file .env.")
        self.client = genai.Client(api_key=api_key)
        self.generation_config = types.GenerateContentConfig(
            max_output_tokens=self.max_new_tokens,
            temperature=self.temperature,
        )

    def generate(self, prompt: str) -> str:
        try:
            if self.provider == "bedrock":
                response = self.client.converse(
                    modelId=self.model_name,
                    messages=[{"role": "user", "content": [{"text": prompt}]}],
                    inferenceConfig={
                        "maxTokens": self.max_new_tokens,
                        "temperature": self.temperature,
                    },
                )
                contents = response.get("output", {}).get("message", {}).get("content", [])
                texts = [item.get("text", "") for item in contents if isinstance(item, dict)]
                return "\n".join(text for text in texts if text).strip()

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self.generation_config,
            )
            if response.text:
                return response.text.strip()
            return ""
        except Exception as exc:
            # Do not present transport/authentication failures as a legal answer
            # or leak provider details to the client.
            print(f"[Generator] {self.provider} request failed: {exc}")
            # Optionally re-raise for debugging? We'll keep returning empty.
            return ""
