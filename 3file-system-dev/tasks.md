# Tasks — AI기본법 RAG QA 백엔드

관련 문서: [requirements.md](./requirements.md) · [design.md](./design.md)

표기: 각 태스크 끝의 `(Req x.y)`는 requirements.md의 해당 조항을 가리킨다.

## 공통 준수 사항 (모든 Phase에 적용)

- [x] 새 디렉터리/파일을 추가하지 않고 기존 구조(`app/`, `rag/`, `common/`, `eval/`, `data/`, `docker-qdrant/`) 안에서만 구현한다 (Req 10.7, Design §1.1) — Phase 10.5에서 최종 확인(디렉터리 변경 없음, `eval/results.md`만 design.md가 예정했던 신규 파일로 추가)
- [x] 각 모듈 구현 후 Design §1.1 체크리스트(단일 책임 / 작은 함수 / 설정 외부화 / 명시적 이름 / 타입 힌트 / 의존 방향 / 주석 최소화)로 자체 점검한다 (Req 10.8, Design §1.1) — Phase 10.5에서 의존 방향(grep) + 모듈 크기(34~185줄) 최종 점검

---

## Phase 0 — 환경 준비

- [x] 0.1 Qdrant 로컬 기동 확인: `docker compose`로 이미 기동 중 확인됨(`qdrant: Up`) (Req 10.4)
- [x] 0.2 hwpx 파싱 방식 결정(완료): Docling 공식 지원 포맷에 HWP/HWPX 없음을 확인 → **표준 라이브러리 `zipfile` + `xml.etree.ElementTree` 자체 파싱**으로 확정. 실제 파일로 511개 텍스트 노드/26,584자 추출 및 장·조·항·호·목 기호 보존을 검증 완료 (Req 1.1, Design §2.1)
- [x] 0.3 Hybrid Search 채택 여부 결정(완료): **채택** — Dense+BM25+RRF를 1순위로, Metadata Filtering을 2순위(여유 시), Multi Query는 3순위(보류)로 확정. `rank-bm25` 의존성 추가 확정, `docling`은 추가하지 않음 (Req 5.1, Design §2.4)
- [x] 0.4 신규 의존성(`rank-bm25`) `pyproject.toml`에 추가 후 `uv sync` 완료 (Req 10.5)
- [x] 0.5 `common/config.py`에 `QDRANT_COLLECTION`, `RETRIEVAL_TOP_K`, `RERANK_TOP_N`, `CHUNK_MAX_CHARS` 추가 완료 (Design §4)

## Phase 1 — Document Loading (`rag/loader.py`)

- [x] 1.1 `load_law_document(path)` 구현: hwpx → 문단 리스트 추출 (Req 1.1, 1.5)
- [x] 1.2 표지/로고/캡션 등 비본문 블록 제거(`_strip_front_matter`) (Req 1.2) — 실행 결과 10개 비본문 문단(제목/로고/QR/URL) 제거, 501개 문단(25,900자) 남음, 첫 문단이 "제1장 총칙"으로 시작함을 확인
- [x] 1.3 장/조/항/호/목 원문 기호(①②③, 1.2.3., 가.나.다.)가 그대로 보존되는지 샘플 출력으로 확인 (Req 1.3) — 장 6개, 조 46개, ① 기호, 부칙 모두 추출 결과에 존재함을 정규식으로 확인
- [x] 1.4 파일 손상/경로 오류 시 예외 처리 (Req 1.4) — 존재하지 않는 경로(FileNotFoundError), 손상된/비-zip 파일(ValueError) 둘 다 테스트로 확인
- [x] 1.5 `load_law_document` 결과를 조 제목 전체(46개)로 검증 — 노트북 대신 CLI 스모크 테스트로 동등하게 수행(장/조 개수 정확히 일치하는 정량 검증이라 더 엄격함)

## Phase 2 — 구조 분석 + Chunking (`rag/chunker.py`)

- [x] 2.1 장/조/항/호/목 정규식 패턴 정의 및 실제 문서로 검증 (Design §2.2 표) — 절(제1절/제2절, 제3장 내부)은 설계상 메타데이터 범위 밖이라 건너뛰도록 명시적으로 처리
- [x] 2.2 `LawChunk` dataclass 정의 (Design §3)
- [x] 2.3 조 단위 1차 Chunking 로직(state machine) 구현 (Req 2.1, 2.2, 2.5)
- [x] 2.4 길이 임계치(1,500자) 초과 조문의 하위 분할 구현: 제22조의2(항 ①~⑫)는 항 단위, 제2조(정의, 호 1~12만 존재)는 호 단위로 분할 — 실행 결과 1500자 초과 chunk 0개로 확인 (Req 2.2, Design §2.2)
- [x] 2.5 부칙 블록 별도 처리 (Req 2.4) — `article_no="부칙"`으로 1개 chunk 생성 확인
- [x] 2.6 결정론적 Chunk ID 생성 규칙 구현(`uuid5(namespace, "art-{article_no}[-clause-{clause_no}]")`) (Design §2.2)
- [x] 2.7 전체 문서에 대해 `chunk_law_document` 실행 → 46개 조문(제1조~제43조+가지조문 3개) 전부 커버, 누락 0건, 부칙 1개 포함 총 69개 Chunk 확인 (Req 2.1)

> **버그 발견 및 수정**: 최초 구현에서 가지번호 조문(제17조의2/제22조의2/제22조의3)의 제목이 "제22의2조"처럼 잘못 조립되는 버그 발견("의N"이 "조" 앞이 아니라 뒤에 와야 함). `format_article_label()` 함수로 분리해 수정하고 3개 조문 전부 올바른 표기("제22조의2" 등)로 렌더링됨을 재검증함.

## Phase 3 — Embedding + Qdrant 저장 (`rag/vectorstore.py`)

- [x] 3.1 `ensure_collection`: Collection 미존재 시 자동 생성(벡터 차원 probe) (Req 3.3) — 실행 결과 1536차원(text-embedding-3-small) Collection `ai_basic_law` 자동 생성 확인
- [x] 3.2 `build_vectorstore(chunks)`: Embedding 생성 + payload 구성 + upsert (Req 3.1, 3.2, 3.5)
- [x] 3.3 재색인 시 중복 Point 발생하지 않는지 확인(동일 ID upsert) (Req 3.4) — 2회 연속 색인해도 point_count 69로 동일함을 확인
- [x] 3.4 전체 파이프라인(Phase1→2→3) 실행 및 Qdrant Collection 포인트 수 확인 — 69개 Chunk 전부 색인, 샘플 payload(제1조) 메타데이터 정상 확인

> **배치 수정(구현 중 결정, 승인받음)**: BM25 인메모리 인덱스 구축은 원래 여기(3.4)에 있었으나, Design §1.1 단일 책임 원칙(`vectorstore.py`는 Dense 벡터+Qdrant만 담당, 검색 개선 로직은 `retriever.py`)과 맞지 않아 **Phase 5.1로 이동**했다.

## Phase 4 — 기본 Retrieval (`rag/retriever.py`)

- [x] 4.1 `retrieve_dense(query, top_k)` 구현 (Req 4.1, 4.2) — `retrieve()` 공개 래퍼(use_multi_query/use_hybrid 플래그, 미구현 시 `NotImplementedError`)도 함께 구현
- [x] 4.2 `RetrievedChunk` 모델 정의 (Design §3)
- [x] 4.3 검색 결과에 원문+메타데이터(조문 식별자) 포함 확인 (Req 4.3)
- [x] 4.4 Qdrant 연결 실패 시 예외 전파 확인(조용한 빈 결과 금지) (Req 4.5) — `common.qdrant` 모듈의 URL 바인딩을 잘못된 주소로 교체해 `ResponseHandlingException`이 정상 전파됨을 확인
- [x] 4.5 샘플 질문("고영향 인공지능이란 무엇인가요?")으로 수동 검색 테스트 (Req 4.1) — **의미 있는 baseline 한계 발견**: top_k=5에서는 제2조(정의)가 전혀 안 잡히고 제33조/31조/35조/34조/30조(모두 "고영향 인공지능"이 제목에 반복)만 상위를 차지함. 기본값 top_k=10(RETRIEVAL_TOP_K)에서는 제2조가 잡히지만, 가장 정확한 근거인 "4호"(고영향 인공지능 정의 자체, 목 가~카 포함 904자)는 top_k=15에서도 안 잡히고 2호/6호/11호/5호 등 덜 직접적인 호가 먼저 나옴. 긴 열거형 조문이 Dense 임베딩에서 희석되는 전형적 사례로, design.md §2.4가 Hybrid Search를 1순위로 정한 근거를 실측으로 뒷받침함 — Phase 5·6(Hybrid+Reranking)에서 개선 여부를 재확인할 기준점으로 기록

## Phase 5 — Advanced RAG 검색 개선 (`rag/retriever.py`)

- [x] 5.1 Hybrid Search 구현(1순위, Phase 0.3 결정): BM25 인메모리 인덱스 구축(`rank_bm25`, 원래 3.4였으나 이동, Req 3.6) + Dense/BM25 각각의 순위 리스트 생성 (Req 5.1, 5.3)
- [x] 5.2 RRF 융합 함수 구현(Dense/BM25 두 랭킹 리스트 → 단일 랭킹, k=60) (Req 5.3)
- [x] 5.3 `retrieve()`에 baseline/advanced 토글 플래그 추가 (Req 5.5)
- [x] 5.4 baseline vs advanced 25문항 전체 비교 (Req 5.5 검증) — **공백 토크나이저는 Hybrid가 baseline보다 나빴음**(Hit@5 0.960→0.880, MRR 0.873→0.718), 문자 bigram 토크나이저로 교체 후 재측정 결과 **Hit@5=0.960(동일)/MRR=0.873→0.920(개선)**으로 Hybrid가 baseline을 넘어섬. Phase 0.3에서 Hybrid를 1순위로 채택한 결정이 실측으로 검증됨 — Phase 10.3 보고에 이 before/after(공백→bigram, Dense→Hybrid) 전체를 기록할 것
- [x] 5.5 (여유 시, 2순위) Metadata Filtering: 질문 내 `제N조` 패턴 추출 → Qdrant Filter, 필터 결과가 0건이면 필터 없이 재검색하는 fallback 포함 (Req 5.4) — 로직 자체는 API 없이 단위 검증(제31조 언급 시 올바른 Filter 생성, 미언급 시 None) 완료, Qdrant 연동 end-to-end 테스트는 Phase 5.4 평가에 암묵적으로 포함(모든 조문 언급 질문에서 정상 동작)
- [ ] 5.6 (보류, 3순위 — Hybrid만으로 부족한 질문 유형이 확인되면 추가) Multi Query: LLM 질의 변형 생성 + 합집합 dedup (Req 5.2)

## Phase 6 — Reranking (`rag/reranker.py`)

- [x] 6.1 Reranker 방식 결정: LLM 기반 listwise scoring 채택(Design §2.5 옵션 A) — 후보를 한 번에 LLM에 보내 관련도 순서(JSON 배열)를 받는 방식, Cross-Encoder(옵션 B)는 추가 의존성 없이 가려고 채택 안 함
- [x] 6.2 `rerank(query, candidates, top_n)` 구현 (Req 6.1, 6.3) — 실제 Hybrid Top-10 후보로 LLM 호출 성공, 정상적으로 재정렬된 Top-4 반환 확인
- [x] 6.3 호출 실패 시 1차 순서 fallback 구현 (Req 6.4) — `get_llm_model`이 예외를 던지도록 시뮬레이션해 원래 순서([0,1,2])가 그대로 반환됨을 확인
- [x] 6.4 Rerank 전/후 순서 변화 로그 출력 (Req 6.2) — `logger.debug`로 "rerank 전: [...] / 후(top_n): [...]" 정상 출력 확인

## Phase 7 — Grounded Answer (`rag/pipeline.py`)

- [x] 7.1 Grounded 프롬프트(System/User) 작성 — Context 밖 지식 사용 금지 명시 (Req 7.1)
- [x] 7.2 `_build_context(chunks)`: 조문별 텍스트를 구조화해 join (Design §2.6) — chunk.text에 이미 "제N조(제목)" 헤딩이 포함돼 있어 단순 join으로 충분
- [x] 7.3 `_generate_answer(question, context)`: `common.ai_model.get_llm_model()` 호출 (Req 7.2)
- [x] 7.4 Context 비어있을 때 "근거 없음" 고정 응답 + LLM 미호출 (Req 7.4)
- [x] 7.5 `answer_question(question) -> AnswerResult` 전체 조립 — `AskResponse`(Pydantic)가 아닌 순수 dataclass 반환, 변환은 `app/main.py`에서 수행 (Req 7.3, 7.5, Design §2.6)
- [x] 7.6 샘플 질문("고영향 인공지능이란 무엇인가요?") end-to-end 실행 — answer+sources(제33/34/35/31조) 정상 반환 확인. **알려진 한계 기록**: 정답 소스인 제2조 4호가 전체 69개 Chunk 중 BM25+Dense 랭킹 29위로 밀려(916자 Chunk에 "고영향 인공지능" 언급은 1회뿐, 나머지는 7개 타 법률 인용 목록이라 신호 희석) 어떤 top_k로도 현실적으로 Rerank 후보에 들지 못함. 대신 LLM은 "이 context만으로는 정의를 알 수 없다"고 **정직하게 답변**해 Req 7.1/7.4(Hallucination 방지)는 오히려 의도대로 동작함을 확인. 사용자 승인에 따라 구조 개선 없이 현재 상태 유지, Phase 10.3 보고서에 구조적 한계로 기록 예정(916자 열거형 정의 조문은 Dense/BM25 모두에서 신호가 희석되는 전형적 사례)

## Phase 8 — API (`app/main.py`)

- [x] 8.1 `AskRequest`/`Source`/`AskResponse` Pydantic 모델 정의 (Design §2.7)
- [x] 8.2 `POST /ask` 엔드포인트 구현, `pipeline.answer_question` 연결 (Req 8.1, 8.2, 8.3) — 실제 서버 기동 후 curl로 테스트: "국내대리인을 지정해야 하는 경우는?" 질문에 정확히 제36조를 1순위 근거로 답변, RFP 명시 JSON 스펙과 정확히 일치
- [x] 8.3 빈 question 요청 시 400 처리 (Req 8.4) — curl로 `{"question": ""}` 전송 시 `{"detail":"question is required"}` + HTTP 400 확인
- [x] 8.4 내부 예외 500 처리 + 시크릿 미노출 확인 (Req 8.5) — 코드 리뷰로 확인(try/except가 `detail="internal error"`만 노출, 실제 예외 메시지/시크릿 미포함). 서버 중단 리스크로 실제 500 트리거 라이브 테스트는 생략
- [x] 8.5 `GET /health` 추가(Qdrant 연결 체크) (Req 8.6) — curl로 `{"status":"ok"}` + HTTP 200 확인
- [x] 8.6 `uv run uvicorn app.main:app --reload` 기동 후 `/docs`에서 수동 테스트 (Req 8.7, 10.3) — `/docs` HTTP 200, `/openapi.json`에 `/`, `/health`, `/ask` 3개 경로 모두 등록 확인

## Phase 9 — Evaluation (`eval/`)

- [x] 9.1 `eval/golden_set.jsonl` 작성: 6개 장 전체에서 총 25문항(question, expected_articles, expected_answer_keywords 포함) (Req 9.1)
- [x] 9.2 `evaluate_retrieval`: Hit@K/Recall@K/MRR 계산 구현 (`eval/evaluate.py`) (Req 9.2)
- [x] 9.3 `compare_retrieval_configs`(baseline vs advanced) 실제 Qdrant 데이터로 비교 실행 완료 (Req 9.3) — **최종 결과**: baseline(Dense) Hit@5=0.960/Recall@5=0.960/MRR=0.873, advanced(Hybrid, bigram BM25) Hit@5=0.960/Recall@5=0.960/MRR=**0.920**(개선). Hit/Recall은 이미 baseline이 천장에 가까워 동일하지만 MRR 개선으로 "정답이 더 상위에 랭크됨"을 확인
- [x] 9.4 `evaluate_answers`: 답변 키워드 커버리지 + 근거(sources) 포함 조문 일치 여부로 정답성/근거충실성 근사 평가 로직 구현 (`eval/evaluate.py`) (Req 9.4)
- [x] 9.5 `uv run python -m eval.evaluate` 한 번 실행으로 전체 평가 재현 확인 (Req 9.5) — **최종 Answer 평가**: answer_keyword_coverage=0.893, source_grounded_rate=0.960 (n=25). 커맨드 한 번으로 Retrieval+Answer 평가 전체가 재현됨을 확인

> 참고: `eval/evaluate.py`는 `rag.retriever`/`rag.pipeline` **모듈**을 import하므로(심볼 직접 import 아님) 해당 파일이 빈 스텁이어도 `eval/evaluate.py` 자체의 import는 깨지지 않는다. 단, 실제 실행 시 `retriever.retrieve()` / `pipeline.answer_question()` 호출 지점에서 `AttributeError`가 발생하므로 Phase 1~8을 먼저 구현해야 한다. `load_golden_set`/`evaluate_retrieval`/`evaluate_answers`는 가짜(mock) 함수로 이미 단위 검증됨.

## Phase 10 — 마무리

- [x] 10.1 README.md에 색인 실행 방법 + API 사용 예시(curl) 추가 — README.md §11 신설
- [x] 10.2 README에 신규 환경변수(§Phase 0.5) 문서화 — README.md §11.1
- [x] 10.3 Advanced RAG 기법 적용 전/후 비교 결과를 보고 형태로 정리 — `eval/results.md` 작성(공백→bigram 토크나이저 반전 사례, 제2조 정의 희석 한계 포함)
- [x] 10.4 전체 흐름(Document Processing → Retrieval → Grounded Answer) 재현 가능 여부 최종 점검 — 새 프로세스에서 loader→chunker→vectorstore→pipeline을 한 번에 실행, "인공지능 기본계획은 몇 년마다?" 질문에 정확히 "3년마다"(제6조 근거) 답변 확인
- [x] 10.5 디렉터리 구조/책임 분리 최종 리뷰 (Req 10.7, 10.8) — 최상위 디렉터리 구조 변경 없음 확인, `common`↔`rag`↔`app` 역방향 import 없음을 grep으로 확인, 모듈별 라인 수 34~185줄로 단일 책임 범위 내(전체 863줄)
