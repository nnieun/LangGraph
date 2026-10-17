from langchain_openai import ChatOpenAI
from langchain_openai import OpenAIEmbeddings
from langchain_core.rate_limiters import InMemoryRateLimiter
import common.config as config

from common.config import (
    BASE_URL,
    EMBEDDING_MODEL,
    LLM_API_KEY,
    MODEL,
    TEMPERATURE,
    MAX_TOKENS,
)

# MonoRouter 제한(분당 30회)보다 여유 있게 초당 0.4회로 제한한다.
_LLM_RATE_LIMITER = InMemoryRateLimiter(
    requests_per_second=0.4,
    check_every_n_seconds=0.1,
    max_bucket_size=1,
)

def get_llm_model(
    model: str | None = None,
    api_key: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
):
    model = model or config.MODEL
    api_key = api_key or config.LLM_API_KEY
    temperature = config.TEMPERATURE if temperature is None else temperature
    max_tokens = config.MAX_TOKENS if max_tokens is None else max_tokens

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=BASE_URL,
        temperature=temperature,
        max_tokens=max_tokens,
        use_responses_api=False,
        rate_limiter=_LLM_RATE_LIMITER,
    )


def get_embedding_model():
    embedding_model = EMBEDDING_MODEL
    embeddings = OpenAIEmbeddings(
        api_key=LLM_API_KEY,
        base_url=BASE_URL,
        model=embedding_model,
    )
    return embeddings

# mono key로 할 때는 아래처럼 해야 함. (MonoRouter 사용)
# def get_llm_model(
#     model: str = MODEL,
#     api_key: str = API_KEY,
#     temperature: float = 0,
#     max_tokens: int = 512
# ):
#     return ChatOpenAI(
#         model=MODEL,
#         api_key=API_KEY,
#         base_url=BASE_URL,
#         temperature=temperature,
#         use_responses_api=False,  # base url로 할 때는 이부분 넣어야 함.(MonoRouter 사용)
#         max_tokens=max_tokens,
#     )


# def get_embedding_model():
#     embedding_model = EMBEDDING_MODEL
#     embeddings = OpenAIEmbeddings(
#         api_key=API_KEY,
#         base_url=BASE_URL,
#         model=embedding_model
#         )
#     # print(embeddings)
#     return embeddings
