from __future__ import annotations

from typing import Any, Dict, Optional

from .generator import GeneratorService
from .prompt import build_prompt
from .retriever import Retriever


class QAService:
    def __init__(
        self,
        retriever: Optional[Retriever] = None,
        generator: Optional[GeneratorService] = None,
    ) -> None:
        self.retriever = retriever or Retriever()
        self.generator = generator or GeneratorService()

    def ask(self, question: str, top_k: Optional[int] = None) -> Dict[str, Any]:
        retrieval = self.retriever.retrieve_with_context(question, top_k=top_k)
        prompt = build_prompt(question, retrieval["results"])
        answer = self.generator.generate(prompt)

        return {
            "question": question,
            "answer": answer,
            "top_k": retrieval["top_k"],
            "results": retrieval["results"],
            "context": retrieval["context"],
            "prompt": prompt,
        }