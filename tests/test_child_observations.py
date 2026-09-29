from __future__ import annotations

from app import mock_llm
from app.agent import LabAgent
from app.mock_rag import retrieve


class RecordingGenerationClient:
    def __init__(self) -> None:
        self.generation_updates: list[dict] = []

    def update_current_generation(self, **kwargs) -> None:
        self.generation_updates.append(kwargs)


def test_retrieve_and_generate_are_wrapped_as_observations() -> None:
    assert hasattr(retrieve, "__wrapped__")
    assert hasattr(mock_llm.FakeLLM.generate, "__wrapped__")


def test_generation_records_model_usage_and_cost_matching_log_cost(monkeypatch) -> None:
    client = RecordingGenerationClient()
    monkeypatch.setattr(mock_llm, "get_langfuse_client", lambda: client)

    response = mock_llm.FakeLLM(model="claude-sonnet-4-5").generate("Feature=qa\nDocs=d\nQuestion=hi")

    (update,) = client.generation_updates
    assert update["model"] == "claude-sonnet-4-5"
    assert update["usage_details"] == {
        "input": response.usage.input_tokens,
        "output": response.usage.output_tokens,
    }
    assert update["cost_details"]["total"] == LabAgent()._estimate_cost(
        response.usage.input_tokens, response.usage.output_tokens
    )
    assert update["completion_start_time"] is not None
    assert "input" not in update and "output" not in update
