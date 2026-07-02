from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr
from core.config import settings

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=SecretStr(settings.OPENAI_API_KEY),
    max_retries=3,
)


async def embed_text(text: str) -> list[float]:
    return await embeddings.aembed_query(text)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return await embeddings.aembed_documents(texts)
