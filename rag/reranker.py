import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from common.ai_model import get_llm_model
from common.config import RERANK_TOP_N
from rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "너는 인공지능기본법 조문 검색 결과를 질문과의 관련도 순으로 재정렬하는 도우미다. "
    "반드시 JSON 배열(관련도 높은 순 후보 번호 목록)만 출력하고 다른 설명을 덧붙이지 않는다."
)
_CANDIDATE_TEXT_PREVIEW_CHARS = 300


def rerank(query: str, candidates: list[RetrievedChunk], top_n: int = RERANK_TOP_N) -> list[RetrievedChunk]:
    """LLM으로 후보를 관련도 순 재정렬해 상위 top_n개를 반환한다(실패 시 원래 순서 유지)."""
    if not candidates:
        return []

    try:
        order = _rank_by_llm(query, candidates)
    except Exception:
        logger.warning("Reranking 실패, 1차 검색 순서로 대체합니다", exc_info=True)
        order = list(range(len(candidates)))

    before = [c.chunk.article_no for c in candidates]
    reranked = [candidates[i] for i in order]
    after = [c.chunk.article_no for c in reranked[:top_n]]
    logger.debug("rerank 전: %s / 후(top_n): %s", before, after)

    return reranked[:top_n]


def _rank_by_llm(query: str, candidates: list[RetrievedChunk]) -> list[int]:
    """LLM을 호출해 관련도 순 후보 인덱스 리스트를 받는다."""
    llm = get_llm_model()
    response = llm.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=_build_prompt(query, candidates)),
        ]
    )
    return _parse_order(response.content, len(candidates))


def _build_prompt(query: str, candidates: list[RetrievedChunk]) -> str:
    """질문과 번호 붙인 후보(본문 앞 300자)로 재정렬 요청 프롬프트를 만든다."""
    listed = "\n".join(
        f"[{i}] {c.chunk.text[:_CANDIDATE_TEXT_PREVIEW_CHARS]}" for i, c in enumerate(candidates)
    )
    return (
        f"질문: {query}\n\n후보 조문:\n{listed}\n\n"
        "질문과 관련도가 높은 순서대로 후보 번호를 JSON 배열로만 출력하라. "
        "예시: [2, 0, 1]"
    )


def _parse_order(raw_response: str, candidate_count: int) -> list[int]:
    """LLM 응답의 JSON 배열을 파싱해 유효 인덱스만 남기고, 누락된 인덱스는 뒤에 붙인다."""
    match = re.search(r"\[[\d,\s]*\]", raw_response)
    if not match:
        raise ValueError(f"재정렬 응답에서 JSON 배열을 찾지 못했습니다: {raw_response!r}")

    order = json.loads(match.group())
    valid = [i for i in order if isinstance(i, int) and 0 <= i < candidate_count]
    missing = [i for i in range(candidate_count) if i not in valid]
    return valid + missing
