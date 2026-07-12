"""
NeuroWeave Python SDK — low-level HTTP client

Wraps the NeuroWeave Cognitive Runtime REST API. Works against any
deployment (local dev server, self-hosted, or a managed NeuroWeave
endpoint) — just point `base_url` at it.
"""
from typing import Any, Dict, List, Optional

import httpx


class NeuroWeaveClient:
    """Thin, synchronous HTTP client for the NeuroWeave Cognitive Runtime API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: float = 60.0,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        headers = {"X-API-Key": api_key} if api_key else {}
        self._client = httpx.Client(
            base_url=self.base_url, headers=headers, timeout=timeout, transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "NeuroWeaveClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    # --- Cognitive Runtime ---

    def chat(self, user_id: str, message: str, **kwargs: Any) -> Dict[str, Any]:
        payload = {"user_id": user_id, "message": message, **{k: v for k, v in kwargs.items() if v is not None}}
        return self._request("POST", "/runtime/chat", json=payload)

    def health(self) -> Dict[str, Any]:
        return self._request("GET", "/runtime/health")

    def version(self) -> Dict[str, Any]:
        return self._request("GET", "/runtime/version")

    def metrics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request("GET", "/runtime/metrics", params={"user_id": user_id} if user_id else {})

    def explain(self, user_id: str, subject_type: str, subject_id: Optional[str] = None) -> Dict[str, Any]:
        params = {"user_id": user_id, "subject_type": subject_type}
        if subject_id:
            params["subject_id"] = subject_id
        return self._request("GET", "/runtime/explain", params=params)

    def benchmark(
        self, user_id: str, query: str,
        history: Optional[List[str]] = None, strategies: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        payload = {"user_id": user_id, "query": query, "history": history or [], "strategies": strategies}
        return self._request("POST", "/runtime/benchmark", json=payload)

    def evaluate(self, dataset_name: str = "synthetic", user_count: int = 3, seed: int = 42) -> Dict[str, Any]:
        payload = {"dataset_name": dataset_name, "user_count": user_count, "seed": seed}
        return self._request("POST", "/runtime/evaluate", json=payload)

    def dashboard(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        return self._request("GET", "/runtime/dashboard", params={"user_id": user_id} if user_id else {})

    def delete_user(self, user_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/runtime/users/{user_id}")

    # --- Memory / cognitive surfaces (Days 1-9) ---

    def ingest_memory(self, user_id: str, conversation: str) -> Dict[str, Any]:
        return self._request("POST", "/memory/ingest", json={"user_id": user_id, "conversation": conversation})

    def retrieve_memory(self, user_id: str, query: str, top_k: int = 10) -> Dict[str, Any]:
        return self._request("POST", "/memory/retrieve", json={"user_id": user_id, "query": query, "top_k": top_k})

    def compose_context(self, user_id: str, query: str) -> Dict[str, Any]:
        return self._request("POST", "/context/compose", json={"user_id": user_id, "query": query})

    def get_world_model(self, user_id: str) -> Dict[str, Any]:
        return self._request("GET", "/world/model", params={"user_id": user_id})

    def list_projects(self, user_id: str) -> Dict[str, Any]:
        return self._request("GET", "/projects", params={"user_id": user_id})
