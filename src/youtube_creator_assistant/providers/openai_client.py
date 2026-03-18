from __future__ import annotations

import os
from typing import Optional

from openai import OpenAI


class OpenAIProvider:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client: Optional[OpenAI] = None

    def client(self) -> OpenAI:
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is missing.")
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key)
        return self._client
