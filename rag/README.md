# rag/ 모듈 설명

인공지능기본법(hwpx)을 대상으로 하는 RAG 파이프라인 모듈이다. **Offline(색인)** 과 **Online(질의응답)** 두 단계로 나뉜다.

```
[Offline]  loader → chunker → vectorstore        (진입점: indexer.py)
[Online]   retriever → reranker → pipeline       (진입점: pipeline.answer_question)
```

| 단계 | 모듈 | 역할 |
|------|------|------|
| Offline | `loader.py` | hwpx 문서 → 문단 텍스트 리스트 |
| Offline | `chunker.py` | 문단 → 조문 단위 `LawChunk` (메타데이터 포함) |
| Offline | `vectorstore.py` | Chunk 임베딩 → Qdrant upsert |
| Offline | `indexer.py` | 위 3단계를 묶은 CLI 진입점 |
| Online | `retriever.py` | Dense / BM25 / Hybrid(RRF) 검색 |
| Online | `reranker.py` | LLM으로 후보 재정렬 후 상위 N개 선택 |
| Online | `pipeline.py` | 검색 → 재정렬 → 답변 생성 → 출처 조립 |

---

## Offline: 색인

### `loader.py`
- `load_law_document(path) -> list[str]`
  - hwpx는 zip 컨테이너이며, `Contents/section0.xml`에서 `<hp:t>` 텍스트를 문단 단위로 추출한다.
  - `제1장`이 처음 나오기 전의 표지, 로고, QR 설명 같은 비본문 블록은 제거한다.
  - 파일이 손상됐거나 구조가 다르면 `ValueError`를 낸다.

### `chunker.py`
- `LawChunk` (dataclass): Qdrant payload로 그대로 저장되는 Chunk 단위
  - `id`, `text`, `chapter_no`, `chapter_title`, `article_no`, `article_title`, `clause_no`, `law_name`, `law_number`, `enforcement_date`
  - `article_no`는 일반 조문이면 `int`(예: `2`), 가지번호 조문이면 `"17의2"`, 부칙이면 `"부칙"`이다.
- `chunk_law_document(paragraphs, max_chars=CHUNK_MAX_CHARS) -> list[LawChunk]`
  - **조문(제N조) 1개 = Chunk 1개**가 기본이다. 장(제N장) 정보는 메타데이터로 붙이고, 절(제N절)은 건너뛴다.
  - 조문 텍스트가 `max_chars`를 넘으면 **항(①②…)** 단위로 나누고, 항이 없으면 **호(1. 2. …)** 단위로 나눈다. 첫 항/호 앞의 도입 문단은 분할된 각 Chunk 앞에 반복해 넣어, Chunk 하나만 읽어도 맥락이 통하게 한다.
  - Chunk `text`는 `"제N조(제목)\n본문"` 형태로 만들어진다.
  - `id`는 조문/항 번호로 만든 **UUIDv5(결정론적)** 라서, 다시 색인해도 중복이 생기지 않고 덮어쓴다.
- `format_article_label(article_no) -> str`: `"22의2"`를 `"제22조의2"`로 바꾸는 표기 변환 함수(pipeline에서도 사용).

### `vectorstore.py`
- `build_vectorstore(chunks)`: Chunk 텍스트를 임베딩(`EMBEDDING_MODEL`)해 `QDRANT_COLLECTION`에 upsert한다.
- `ensure_collection(client, name, vector_size)`: 컬렉션이 없을 때만 Cosine 거리로 생성한다.

### `indexer.py`
- `run_indexing(path) -> int`: load → chunk → upsert를 실행하고 Chunk 수를 반환한다.
- CLI:
  ```bash
  uv run python -m rag.indexer                          # 기본: data/ai_basic_law.hwpx
  uv run python -m rag.indexer --path data/other.hwpx
  ```

---

## Online: 질의응답

### `retriever.py`
- `RetrievedChunk` (dataclass): `chunk: LawChunk`, `score: float`
- `retrieve(query, top_k, use_multi_query=False, use_hybrid=False)`: 검색 방식을 플래그로 고르는 진입점(eval에서 전/후 비교에 사용)
  - `use_multi_query=True`는 아직 구현되지 않아 `NotImplementedError`를 낸다.
- `retrieve_dense(query, top_k)`: Qdrant 벡터 검색
  - 질문에 `제N조`가 들어 있으면 `article_no` **Metadata Filter**로 범위를 좁힌다. 필터를 걸었는데 결과가 없으면 필터 없이 다시 검색한다.
- `retrieve_bm25(query, top_k)`: 키워드 검색
  - Qdrant의 전체 Chunk를 `scroll`로 가져와 BM25 인메모리 인덱스를 **한 번만 만들고 캐싱**한다.
  - 한국어는 조사가 단어에 붙어 공백 기준으로 자르면 정확도가 떨어지므로, **문자 bigram**으로 토큰화한다.
- `retrieve_hybrid(query, top_k)`: Dense와 BM25에서 각각 `max(top_k×3, 20)`개 후보를 가져와 **RRF(Reciprocal Rank Fusion, k=60)** 로 합친다.

### `reranker.py`
- `rerank(query, candidates, top_n=RERANK_TOP_N)`: LLM에게 후보(본문 앞 300자)를 보여주고 관련도 순서를 JSON 배열로 받아 상위 `top_n`개를 반환한다.
  - LLM이 빠뜨린 번호는 원래 순서대로 뒤에 붙이고, 범위를 벗어난 번호는 버린다.
  - LLM 호출이나 파싱에 실패하면 경고 로그를 남기고 **1차 검색 순서를 그대로 사용**한다.

### `pipeline.py`
- `answer_question(question) -> AnswerResult`: Online 전체 흐름
  1. `retrieve(..., use_hybrid=True)`로 `RETRIEVAL_TOP_K`개 후보를 검색한다.
  2. `rerank`로 `RERANK_TOP_N`개를 고른다. 결과가 없으면 "관련 법률 근거를 찾지 못했습니다."를 반환한다.
  3. 고른 Chunk 텍스트를 `<context>`로 묶어 LLM을 호출한다(context에 있는 내용만 근거로 답하도록 시스템 프롬프트로 제한).
  4. 답변과 출처(`AnswerSource(article="제N조", content=...)`)를 조립해 반환한다.
- FastAPI `POST /ask`([app/main.py](../app/main.py))가 이 함수를 호출한다.
- 실행 예:
  ```bash
  uv run uvicorn app.main:app --reload
  # 또는
  uv run python -c "from rag.pipeline import answer_question; print(answer_question('고영향 인공지능이란?').answer)"
  ```

---

## 관련 설정 (`common/config.py`, `.env`)

| 변수 | 기본값 | 사용처 |
|------|--------|--------|
| `QDRANT_URL` | `http://localhost:6333` | vectorstore, retriever |
| `QDRANT_COLLECTION` | `ai_basic_law` | vectorstore, retriever |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | vectorstore, retriever |
| `LLM_MODEL` | `gpt-5.4-mini` | reranker, pipeline |
| `CHUNK_MAX_CHARS` | `1500` | chunker |
| `RETRIEVAL_TOP_K` | `10` | retriever, pipeline |
| `RERANK_TOP_N` | `4` | reranker, pipeline |
