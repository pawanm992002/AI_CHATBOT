import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from services.chat_service import ChatService, ChatTurnInput


class MockLLMResponse:
    def __init__(self, content: str):
        self.content = content


def _make_turn(tenant: dict | None = None, **kwargs) -> ChatTurnInput:
    defaults = {
        "tenant": tenant or {
            "tenant_id": "t1",
            "business_name": "TestBiz",
            "domain": "testbiz.com",
            "description": "A test business",
        },
        "session_id": "sess1",
        "query": "What is your return policy?",
        "visitor_id": "v1",
        "current_url": "https://testbiz.com/faq",
        "current_page_title": "FAQ",
        "message_id": "msg1",
    }
    defaults.update(kwargs)
    return ChatTurnInput(**defaults)


class TestEvaluateAnswerSufficiency(unittest.IsolatedAsyncioTestCase):
    """Unit tests for _evaluate_answer_sufficiency in isolation."""

    async def test_sufficient_answer(self):
        svc = ChatService()
        with patch("services.chat_service.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = MockLLMResponse("SUFFICIENT")
            mock_get_llm.return_value = mock_llm

            result = await svc._evaluate_answer_sufficiency(
                query="What is your return policy?",
                answer="You can return items within 30 days.",
            )

        self.assertEqual(result, "sufficient")

    async def test_insufficient_answer_on_topic(self):
        svc = ChatService()
        with patch("services.chat_service.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = MockLLMResponse("KNOWLEDGE_GAP")
            mock_get_llm.return_value = mock_llm

            result = await svc._evaluate_answer_sufficiency(
                query="What is your return policy?",
                answer="I don't have that information.",
            )

        self.assertEqual(result, "no_context")

    async def test_answer_off_topic_query(self):
        svc = ChatService()
        with patch("services.chat_service.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = MockLLMResponse("OUT_OF_SCOPE")
            mock_get_llm.return_value = mock_llm

            result = await svc._evaluate_answer_sufficiency(
                query="Who won the cricket match?",
                answer="I can only help with questions about TestBiz.",
            )

        self.assertEqual(result, "out_of_scope")

    async def test_llm_exception_failsafe(self):
        svc = ChatService()
        with patch("services.chat_service.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.side_effect = RuntimeError("LLM down")
            mock_get_llm.return_value = mock_llm

            result = await svc._evaluate_answer_sufficiency(
                query="What is your return policy?",
                answer="I don't know.",
            )

        self.assertEqual(result, "sufficient")

    async def test_unexpected_label_defaults_to_no_context(self):
        svc = ChatService()
        with patch("services.chat_service.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = MockLLMResponse("SOMETHING_ELSE")
            mock_get_llm.return_value = mock_llm

            result = await svc._evaluate_answer_sufficiency(
                query="What is your return policy?",
                answer="Maybe?",
            )

        self.assertEqual(result, "no_context")

    async def test_sufficient_with_partial_match_in_string(self):
        svc = ChatService()
        with patch("services.chat_service.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = MockLLMResponse("  sufficient  ")
            mock_get_llm.return_value = mock_llm

            result = await svc._evaluate_answer_sufficiency(
                query="What is your return policy?",
                answer="You can return items within 30 days.",
            )

        self.assertEqual(result, "sufficient")


def _make_chunks() -> list[dict]:
    return [{
        "parent_id": "p1",
        "url": "https://testbiz.com/faq",
        "title": "FAQ",
        "text": "Some context text for testing purposes.",
        "score": 0.75,
        "child_text": "child text",
        "child_index": 0,
    }]


class TestNonStreamingHandlerGapLogging(unittest.IsolatedAsyncioTestCase):
    """Tests _handle_answer_with_chunks (non-streaming, fire-and-forget).

    The evaluator runs via asyncio.ensure_future. We yield to the event loop
    after the handler returns to let the background task complete.
    """

    async def asyncSetUp(self):
        self.svc = ChatService()
        self.chunks = _make_chunks()
        self.turn = _make_turn()

    async def _test(self, gap_type, expect_log, form_id=""):
        with (
            patch.object(self.svc, "_complete_answer") as mock_complete,
            patch.object(self.svc, "_evaluate_answer_sufficiency", new_callable=AsyncMock) as mock_eval,
            patch.object(self.svc, "_log_knowledge_gap", new_callable=AsyncMock) as mock_log,
            patch.object(self.svc, "_compact_if_needed", return_value=("", [])),
            patch.object(self.svc, "_persist_conversation", new_callable=AsyncMock),
            patch.object(self.svc, "_track_visitor_message", new_callable=AsyncMock),
            patch.object(self.svc, "_build_sources", return_value=[]),
        ):
            mock_complete.return_value = ("I don't have that information.", {"total_tokens": 10})
            mock_eval.return_value = gap_type

            result = await self.svc._handle_answer_with_chunks(
                turn=self.turn,
                summary="",
                messages=[],
                chunks=self.chunks,
                needs_search=True,
                form_id=form_id,
                form_title="",
            )

            self.assertIsNotNone(result.answer)

            # Yield to event loop so the ensure_future background task runs
            await asyncio.sleep(0)

            if form_id:
                mock_eval.assert_not_called()
                mock_log.assert_not_called()
            else:
                mock_eval.assert_awaited_once()
                if expect_log:
                    mock_log.assert_awaited_once_with(
                        "t1", self.turn.query, self.turn.current_url, gap_type, self.turn.message_id
                    )
                else:
                    mock_log.assert_not_called()

    async def test_insufficient_answer_logs_gap(self):
        await self._test("no_context", expect_log=True)

    async def test_out_of_scope_answer_logs_gap(self):
        await self._test("out_of_scope", expect_log=True)

    async def test_sufficient_answer_does_not_log_gap(self):
        await self._test("sufficient", expect_log=False)

    async def test_form_id_present_suppresses_gap_logging(self):
        await self._test("no_context", expect_log=False, form_id="form1")


class TestStreamingHandlerGapLogging(unittest.IsolatedAsyncioTestCase):
    """Tests _handle_answer_with_chunks_stream (streaming, inline await).

    Uses await (not ensure_future), so assertions are straightforward.
    """

    async def asyncSetUp(self):
        self.svc = ChatService()
        self.chunks = _make_chunks()
        self.turn = _make_turn()

    async def _test(self, gap_type, expect_log, form_id=""):
        tokens = []

        async def on_token(token):
            tokens.append(token)

        with (
            patch.object(self.svc, "_complete_answer_stream") as mock_stream,
            patch.object(self.svc, "_evaluate_answer_sufficiency", new_callable=AsyncMock) as mock_eval,
            patch.object(self.svc, "_log_knowledge_gap", new_callable=AsyncMock) as mock_log,
            patch.object(self.svc, "_compact_if_needed", return_value=("", [])),
            patch.object(self.svc, "_persist_conversation", new_callable=AsyncMock),
            patch.object(self.svc, "_track_visitor_message", new_callable=AsyncMock),
            patch.object(self.svc, "_build_sources", return_value=[]),
        ):
            async def _stream():
                yield {"answer": "I don't have that information.", "usage": {"total_tokens": 10}}

            mock_stream.return_value = _stream()
            mock_eval.return_value = gap_type

            result = await self.svc._handle_answer_with_chunks_stream(
                turn=self.turn,
                summary="",
                messages=[],
                chunks=self.chunks,
                needs_search=True,
                form_id=form_id,
                form_title="",
                on_token=on_token,
            )

            self.assertIsNotNone(result.answer)

            if form_id:
                mock_eval.assert_not_called()
                mock_log.assert_not_called()
            else:
                mock_eval.assert_awaited_once()
                if expect_log:
                    mock_log.assert_awaited_once_with(
                        "t1", self.turn.query, self.turn.current_url, gap_type, self.turn.message_id
                    )
                else:
                    mock_log.assert_not_called()

    async def test_stream_insufficient_answer_logs_gap(self):
        await self._test("no_context", expect_log=True)

    async def test_stream_out_of_scope_answer_logs_gap(self):
        await self._test("out_of_scope", expect_log=True)

    async def test_stream_sufficient_answer_does_not_log_gap(self):
        await self._test("sufficient", expect_log=False)

    async def test_stream_form_id_present_suppresses_gap_logging(self):
        await self._test("no_context", expect_log=False, form_id="form1")


if __name__ == "__main__":
    unittest.main()
