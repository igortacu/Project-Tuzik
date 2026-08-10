from unittest.mock import Mock, patch

from second_brain.generation.llm_client import ToolResult
from second_brain.pipelines import query_pipeline


def test_answer_query_forwards_chat_id_to_generate_with_tools():
    fake_llm = Mock()
    fake_llm.generate_with_tools.return_value = ToolResult(text="answer")
    fake_retriever = Mock()
    fake_retriever.retrieve.return_value = []

    with (
        patch("second_brain.pipelines.query_pipeline._get_llm_client", return_value=fake_llm),
        patch("second_brain.pipelines.query_pipeline._get_retriever", return_value=fake_retriever),
    ):
        query_pipeline.answer_query("what's on my calendar", chat_id=555)

    assert fake_llm.generate_with_tools.call_args.kwargs["chat_id"] == 555
