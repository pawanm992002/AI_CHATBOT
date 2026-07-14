import unittest
from unittest.mock import AsyncMock, patch

from services.chat_service import ChatService, QueryClass


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

