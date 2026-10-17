import re
from dataclasses import dataclass

from qdrant_client.models import FieldCondition, Filter, MatchValue
from rank_bm25 import BM25Okapi

from qdrant_client import QdrantClient

from common.ai_model import get_embedding_model
from common.config import QDRANT_COLLECTION, RETRIEVAL_TOP_K
from common.qdrant import get_qdrant_client
from rag.chunker import LawChunk

RRF_K = 60
# Hybrid 융합 품질을 위해 각 서브 검색기는 최종 top_k보다 넓은 후보군을 가져온다.
HYBRID_CANDIDATE_MULTIPLIER = 3
HYBRID_MIN_CANDIDATES = 20

_ARTICLE_REFERENCE_PATTERN = re.compile(r"제(\d+)조(?:의(\d+))?")
# 질문의 인용부호로 감싼 용어(예: '고영향 인공지능')를 정의 Chunk의 defined_term과 매칭한다.
_QUOTED_TERM_PATTERN = re.compile(r"[\"'‘’“”]([^\"'‘’“”]+)[\"'‘’“”]")


def _law_chunk_from_payload(payload: dict) -> LawChunk:
    """현재 Chunk 스키마와 노트북의 구형 payload 스키마를 모두 지원한다."""
    if "article_no" in payload:
        return LawChunk(**payload)

    return LawChunk(
        id=str(payload.get("id", "")),
        text=payload.get("text", payload.get("content", "")),
        chapter_no=payload.get("chapter_no"),
        chapter_title=payload.get("chapter_title"),
        article_no=payload.get("article", ""),
        article_title=payload.get("article_title", payload.get("title")),
        clause_no=payload.get("clause_no"),
        defined_term=payload.get("defined_term"),
        law_name=payload.get("law_name", "인공지능기본법"),
        law_number=payload.get("law_number", ""),
        enforcement_date=payload.get("enforcement_date", ""),
    )


@dataclass
class RetrievedChunk:
    chunk: LawChunk
    score: float


def retrieve(
    query: str,
    top_k: int = RETRIEVAL_TOP_K,
    use_multi_query: bool = False,
    use_hybrid: bool = False,
) -> list[RetrievedChunk]:
    """baseline(Dense)과 advanced 기법을 플래그로 토글한다 — eval에서 Before/After 비교용.

    use_multi_query는 Phase 5.6(보류)에서 구현되며, 그 전까지 True로 호출하면
    조용히 Dense로 대체하지 않고 NotImplementedError를 낸다.
    """
    if use_multi_query:
        raise NotImplementedError("Multi Query는 아직 구현되지 않았습니다 (tasks.md Phase 5.6)")
    if use_hybrid:
        return retrieve_hybrid(query, top_k)
    return retrieve_dense(query, top_k)


def retrieve_dense(query: str, top_k: int = RETRIEVAL_TOP_K) -> list[RetrievedChunk]:
    """질문을 임베딩해 Qdrant 벡터 검색을 수행한다('제N조' 언급·인용부호 용어 언급 시 메타데이터 필터 적용).

    제2조(정의)처럼 호(항목) 하나가 여러 목(가~카) 열거를 포함해 길어지면 Dense 임베딩이
    희석돼 정확히 그 용어를 묻는 질문에서도 상위 순위에 오르지 못하는 문제가 있다
    (예: '고영향 인공지능'이란 무엇인가요 → 해당 Chunk가 전체 69개 중 59위).
    질문에 인용부호로 감싼 정의 대상 용어가 있으면 defined_term Metadata Filter로
    해당 Chunk를 직접 지정해, 임베딩 유사도 순위와 무관하게 확실히 찾아낸다.
    """
    client = get_qdrant_client()
    embedding_model = get_embedding_model()
    query_vector = embedding_model.embed_query(query)

    metadata_filter = _extract_metadata_filter(query)
    results = _query_points(client, query_vector, top_k, metadata_filter)
    if metadata_filter is not None and not results:
        # 질문이 존재하지 않는 조문/용어를 가리키는 등 필터가 과도하게 좁았던 경우,
        # 필터 없이 다시 검색해 빈 결과로 조용히 실패하지 않게 한다.
        results = _query_points(client, query_vector, top_k, None)
    return results


def _extract_metadata_filter(query: str) -> Filter | None:
    """질문에서 '제N조' 조문 번호와 인용부호 정의 용어를 찾아 Qdrant Metadata Filter로 결합한다."""
    conditions = [
        condition
        for condition in (_extract_article_condition(query), _extract_defined_term_condition(query))
        if condition is not None
    ]
    return Filter(must=conditions) if conditions else None


def _extract_article_condition(query: str) -> FieldCondition | None:
    """질문에 '제N조' 패턴이 있으면 article_no FieldCondition을 만든다."""
    match = _ARTICLE_REFERENCE_PATTERN.search(query)
    if not match:
        return None
    main_no, branch_no = match.group(1), match.group(2)
    article_no: int | str = f"{main_no}의{branch_no}" if branch_no else int(main_no)
    return FieldCondition(key="article_no", match=MatchValue(value=article_no))


def _extract_defined_term_condition(query: str) -> FieldCondition | None:
    """질문에 인용부호로 감싼 용어가 있으면 defined_term FieldCondition을 만든다."""
    match = _QUOTED_TERM_PATTERN.search(query)
    if not match:
        return None
    return FieldCondition(key="defined_term", match=MatchValue(value=match.group(1)))


def _query_points(
    client: QdrantClient, query_vector: list[float], top_k: int, query_filter: Filter | None
) -> list[RetrievedChunk]:
    """Qdrant query_points를 호출하고 결과 payload를 RetrievedChunk로 변환한다."""
    result = client.query_points(
        collection_name=QDRANT_COLLECTION,
        query=query_vector,
        query_filter=query_filter,
        limit=top_k,
    )
    return [
        RetrievedChunk(chunk=_law_chunk_from_payload(point.payload), score=point.score)
        for point in result.points
    ]


def retrieve_bm25(query: str, top_k: int = RETRIEVAL_TOP_K) -> list[RetrievedChunk]:
    """BM25 키워드 점수 상위 top_k개 Chunk를 반환한다."""
    bm25_index, chunks = _get_bm25_index()
    scores = bm25_index.get_scores(_tokenize(query))
    ranked = sorted(zip(chunks, scores), key=lambda pair: pair[1], reverse=True)
    return [RetrievedChunk(chunk=chunk, score=score) for chunk, score in ranked[:top_k]]


def retrieve_hybrid(query: str, top_k: int = RETRIEVAL_TOP_K) -> list[RetrievedChunk]:
    """Dense와 BM25 후보를 RRF로 융합해 상위 top_k개를 반환한다."""
    candidate_k = max(top_k * HYBRID_CANDIDATE_MULTIPLIER, HYBRID_MIN_CANDIDATES)
    dense_results = retrieve_dense(query, top_k=candidate_k)
    bm25_results = retrieve_bm25(query, top_k=candidate_k)
    fused = _reciprocal_rank_fusion([dense_results, bm25_results])
    return fused[:top_k]


def _reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievedChunk]],
    k: int = RRF_K,
) -> list[RetrievedChunk]:
    """score(d) = Σ 1 / (k + rank_i(d)) 로 여러 랭킹 리스트를 하나로 합친다."""
    fused_scores: dict[str, float] = {}
    chunk_by_id: dict[str, LawChunk] = {}

    for ranked_list in ranked_lists:
        for rank, retrieved in enumerate(ranked_list, start=1):
            chunk_id = retrieved.chunk.id
            fused_scores[chunk_id] = fused_scores.get(chunk_id, 0.0) + 1 / (k + rank)
            chunk_by_id[chunk_id] = retrieved.chunk

    ranked_ids = sorted(fused_scores, key=lambda cid: fused_scores[cid], reverse=True)
    return [RetrievedChunk(chunk=chunk_by_id[cid], score=fused_scores[cid]) for cid in ranked_ids]


_bm25_cache: tuple[BM25Okapi, list[LawChunk]] | None = None


def _get_bm25_index() -> tuple[BM25Okapi, list[LawChunk]]:
    """Qdrant에 색인된 전체 Chunk로 BM25 인메모리 인덱스를 1회 구축해 캐싱한다."""
    global _bm25_cache
    if _bm25_cache is None:
        chunks = _load_all_chunks()
        tokenized_corpus = [_tokenize(chunk.text) for chunk in chunks]
        _bm25_cache = (BM25Okapi(tokenized_corpus), chunks)
    return _bm25_cache


def _load_all_chunks() -> list[LawChunk]:
    """Qdrant 컬렉션의 모든 Chunk payload를 scroll로 읽어 LawChunk로 복원한다."""
    client = get_qdrant_client()
    points, _ = client.scroll(
        collection_name=QDRANT_COLLECTION,
        limit=10_000,
        with_payload=True,
        with_vectors=False,
    )
    return [_law_chunk_from_payload(point.payload) for point in points]


def _tokenize(text: str) -> list[str]:
    """한국어는 조사가 단어에 붙어 공백 토큰화의 정확도가 낮으므로 문자 bigram을 쓴다
    (형태소 분석기 없이도 CJK 텍스트에서 널리 쓰이는 근사법)."""
    compact = re.sub(r"\s+", "", text)
    if len(compact) < 2:
        return [compact] if compact else []
    return [compact[i : i + 2] for i in range(len(compact) - 1)]
