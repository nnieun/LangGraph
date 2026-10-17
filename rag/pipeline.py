from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage

from common.ai_model import get_llm_model
from common.config import RERANK_TOP_N, RETRIEVAL_TOP_K
from rag.chunker import format_article_label
from rag.reranker import rerank
from rag.retriever import RetrievedChunk, retrieve

_SYSTEM_PROMPT = (
    "너는 인공지능기본법 QA 어시스턴트다. 반드시 주어진 <context>의 조문만 근거로 답하라. "
    "context에 없는 내용은 모른다고 답하라."
)
_NO_EVIDENCE_ANSWER = "관련 법률 근거를 찾지 못했습니다."


@dataclass
class AnswerSource:
    article: str  # 예: "제2조"
    content: str


@dataclass
class AnswerResult:
    answer: str
    sources: list[AnswerSource]


def answer_question(question: str) -> AnswerResult:
    """Retrieval(Hybrid) → Rerank → Context 구성 → LLM 호출 → Answer+Source 조립."""
    candidates = retrieve(question, top_k=RETRIEVAL_TOP_K, use_hybrid=True)
    top = rerank(question, candidates, top_n=RERANK_TOP_N)
    if not top:
        return AnswerResult(answer=_NO_EVIDENCE_ANSWER, sources=[])

    context = _build_context(top)
    answer_text = _generate_answer(question, context)
    return AnswerResult(answer=answer_text, sources=_to_sources(top))


def _build_context(chunks: list[RetrievedChunk]) -> str:
    """Chunk 텍스트("제N조(제목)\\n본문" 형태)를 빈 줄로 이어 LLM context를 만든다."""
    return "\n\n".join(c.chunk.text for c in chunks)


def _generate_answer(question: str, context: str) -> str:
    """context만 근거로 답하도록 지시한 프롬프트로 LLM을 호출해 답변을 생성한다."""
    llm = get_llm_model()
    response = llm.invoke(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=f"질문: {question}\n\n<context>\n{context}\n</context>"),
        ]
    )
    return response.content


def _to_sources(chunks: list[RetrievedChunk]) -> list[AnswerSource]:
    """Chunk를 "제N조" 표기와 본문을 가진 AnswerSource 리스트로 변환한다."""
    return [
        AnswerSource(article=format_article_label(c.chunk.article_no), content=c.chunk.text)
        for c in chunks
    ]
