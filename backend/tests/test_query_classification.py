import unittest
from unittest.mock import AsyncMock, patch

from services.chat_service import ChatService, ChatTurnInput, ChatTurnResult, QueryClass


class MockLLMResponse:
    def __init__(self, content: str):
        self.content = content


class TestQueryClassification(unittest.IsolatedAsyncioTestCase):
    async def test_tenant_acronym_query_proceeds_without_llm(self):
        svc = ChatService()
        tenant = {
            "tenant_id": "t1",
            "business_name": "Matrix Olympiad (mof)",
            "domain": "mof",
            "description": "Matrix Olympiad Foundation",
        }

        with patch("services.chat_service.get_llm") as mock_get_llm:
            result = await svc._classify_query(
                "what is mof",
                "",
                [],
                tenant=tenant,
            )

        self.assertEqual(result, QueryClass.PROCEED)
        mock_get_llm.assert_not_called()

    async def test_classifier_receives_business_context(self):
        svc = ChatService()
        tenant = {
            "tenant_id": "t1",
            "business_name": "Matrix Olympiad",
            "domain": "mof.matrixedu.in",
            "description": "Scholarship olympiad for students",
        }

        with patch("services.chat_service.get_llm") as mock_get_llm:
            mock_llm = AsyncMock()
            mock_llm.ainvoke.return_value = MockLLMResponse("PROCEED")
            mock_get_llm.return_value = mock_llm

            result = await svc._classify_query(
                "exam details",
                "",
                [],
                tenant=tenant,
            )

        self.assertEqual(result, QueryClass.PROCEED)
        system_prompt = mock_llm.ainvoke.call_args.args[0][0]["content"]
        self.assertIn("Business context", system_prompt)
        self.assertIn("Matrix Olympiad", system_prompt)
        self.assertIn("mof.matrixedu.in", system_prompt)

    async def test_out_of_scope_classification_still_allows_search(self):
        svc = ChatService()
        tenant = {
            "tenant_id": "t1",
            "business_name": "Matrix Olympiad (mof)",
            "domain": "mof",
            "description": "Matrix Olympiad Foundation",
        }
        turn = ChatTurnInput(
            tenant=tenant,
            session_id="sess1",
            query="What was the cash prize of 2025",
            visitor_id="v1",
            message_id="msg1",
        )
        chunks = [{
            "parent_id": "p1",
            "url": "faq://cash-prize",
            "title": "What was the cash prize of 2025?",
            "text": "Q: What was the cash prize of 2025?\nA: 31 Lakh Rs",
            "score": 0.8,
        }]

        with (
            patch.object(svc, "_handle_school_flow", new_callable=AsyncMock, return_value=None),
            patch.object(svc, "_load_conversation_context", new_callable=AsyncMock, return_value=("", [])),
            patch.object(svc, "_classify_query", new_callable=AsyncMock, return_value=QueryClass.OUT_OF_SCOPE),
            patch.object(svc, "_prepare_search", new_callable=AsyncMock, return_value=("cash prize amount for 2025", None, None, "", "")),
            patch.object(svc, "_search_chunks", new_callable=AsyncMock, return_value=(chunks, 0.8)),
            patch.object(svc, "_handle_out_of_scope", new_callable=AsyncMock) as mock_out_of_scope,
            patch.object(svc, "_handle_answer_with_chunks", new_callable=AsyncMock) as mock_answer,
        ):
            mock_answer.return_value = ChatTurnResult(
                message_id="msg1",
                answer="31 Lakh Rs",
                sources=[],
            )

            result = await svc.handle_message(turn)

        self.assertEqual(result.answer, "31 Lakh Rs")
        mock_out_of_scope.assert_not_called()
        mock_answer.assert_awaited_once()
