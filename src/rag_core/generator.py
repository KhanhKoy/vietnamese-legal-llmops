from __future__ import annotations

import os
from typing import Optional

from transformers import pipeline


class GeneratorService:
    def __init__(
        self,
        model_name: Optional[str] = None,
        max_new_tokens: int = 256,
        temperature: float = 0.2,
    ) -> None:
        self.model_name = model_name or os.getenv("LLM_MODEL_NAME", "")
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature

        if not self.model_name:
            self.generator = None
            return

        self.generator = pipeline(
            task="text-generation",
            model=self.model_name,
            tokenizer=self.model_name,
        )

    def generate(self, prompt: str) -> str:
        if self.generator is None:
            raise ValueError(
                "Chưa cấu hình LLM_MODEL_NAME. Hãy đặt biến môi trường hoặc truyền model_name."
            )

        output = self.generator(
            prompt,
            max_new_tokens=self.max_new_tokens,
            do_sample=self.temperature > 0,
            temperature=self.temperature,
            return_full_text=False,
        )

        if isinstance(output, list) and output:
            return str(output[0].get("generated_text", "")).strip()

        return str(output).strip()