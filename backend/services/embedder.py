from openai import AsyncOpenAI
from core.config import settings
from tenacity import retry, stop_after_attempt, wait_exponential

openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
EMBEDDING_MODEL = "text-embedding-3-small"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_text(text: str) -> list[float]:
    response = await openai_client.embeddings.create(
        input=text,
        model=EMBEDDING_MODEL
    )
    return response.data[0].embedding

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    response = await openai_client.embeddings.create(
        input=texts,
        model=EMBEDDING_MODEL
    )
    return [item.embedding for item in response.data]
