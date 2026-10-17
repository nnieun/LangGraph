import re
import uuid
from dataclasses import dataclass, field

from common.config import CHUNK_MAX_CHARS

LAW_NAME = "인공지능기본법"
LAW_NUMBER = "법률 제21311호"
ENFORCEMENT_DATE = "2026-07-21"

_CHUNK_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "rag_minipjt.ai_basic_law")

_CHAPTER_PATTERN = re.compile(r"^제(\d+)장\s*(.+)$")
# 절(예: 제1절)은 design.md §2.2가 정의한 메타데이터(장/조/항/호)에 없어 건너뛴다.
_SECTION_PATTERN = re.compile(r"^제\d+절")
_ARTICLE_PATTERN = re.compile(r"^제(\d+)조(?:의(\d+))?\(([^)]+)\)")
_ADDENDUM_PATTERN = re.compile(r"^부칙$")
_CLAUSE_PATTERN = re.compile(r"^([①-⑮])")
_ITEM_PATTERN = re.compile(r"^(\d+)\.\s")
# 정의 조문(제2조 등)의 "“용어”란/이란" 패턴에서 정의 대상 용어를 추출한다.
_DEFINED_TERM_PATTERN = re.compile(r"[“\"']([^”\"']+)[”\"']\s*(?:이란|란)")


@dataclass
class LawChunk:
    id: str
    text: str
    chapter_no: int | None
    chapter_title: str | None
    article_no: int | str  # 부칙은 "부칙", 가지번호 조문은 "17의2"
    article_title: str | None
    clause_no: str | None = None  # "①" 또는 "1호" 등, 하위 분할된 경우만
    defined_term: str | None = None  # 정의 조문에서 "“용어”란"으로 추출된 용어(없으면 None)
    law_name: str = LAW_NAME
    law_number: str = LAW_NUMBER
    enforcement_date: str = ENFORCEMENT_DATE


@dataclass
class _ArticleBuffer:
    chapter_no: int | None
    chapter_title: str | None
    article_no: int | str
    article_title: str | None
    paragraphs: list[str] = field(default_factory=list)


def chunk_law_document(paragraphs: list[str], max_chars: int = CHUNK_MAX_CHARS) -> list[LawChunk]:
    """문단 리스트를 장/조/부칙 구조로 파싱해 조문 단위 LawChunk 리스트로 만든다."""
    chunks: list[LawChunk] = []
    current_chapter_no: int | None = None
    current_chapter_title: str | None = None
    buffer: _ArticleBuffer | None = None

    for paragraph in paragraphs:
        stripped = paragraph.strip()

        chapter_match = _CHAPTER_PATTERN.match(stripped)
        if chapter_match:
            chunks.extend(_flush(buffer, max_chars))
            buffer = None
            current_chapter_no = int(chapter_match.group(1))
            current_chapter_title = chapter_match.group(2)
            continue

        if _SECTION_PATTERN.match(stripped):
            continue

        if _ADDENDUM_PATTERN.match(stripped):
            chunks.extend(_flush(buffer, max_chars))
            buffer = _ArticleBuffer(
                chapter_no=None,
                chapter_title=None,
                article_no="부칙",
                article_title=None,
            )
            continue

        article_match = _ARTICLE_PATTERN.match(stripped)
        if article_match:
            chunks.extend(_flush(buffer, max_chars))
            buffer = _ArticleBuffer(
                chapter_no=current_chapter_no,
                chapter_title=current_chapter_title,
                article_no=_parse_article_no(article_match),
                article_title=article_match.group(3),
            )
            continue

        if buffer is not None:
            buffer.paragraphs.append(paragraph)

    chunks.extend(_flush(buffer, max_chars))
    return chunks


def _parse_article_no(article_match: re.Match) -> int | str:
    """조문 정규식 매치에서 조 번호를 꺼낸다(가지번호가 있으면 "17의2" 문자열)."""
    main_no, branch_no = article_match.group(1), article_match.group(2)
    return f"{main_no}의{branch_no}" if branch_no else int(main_no)


def _flush(buffer: _ArticleBuffer | None, max_chars: int) -> list[LawChunk]:
    """누적 중인 조문 버퍼를 Chunk로 변환한다(버퍼가 없으면 빈 리스트)."""
    if buffer is None:
        return []
    return _build_chunks(buffer, max_chars)


def _build_chunks(buffer: _ArticleBuffer, max_chars: int) -> list[LawChunk]:
    """조문 전체가 max_chars 이하면 Chunk 1개로, 초과하면 항/호 단위로 분할한다."""
    full_text = _render_text(buffer, buffer.paragraphs)
    if len(full_text) <= max_chars:
        defined_term = _extract_defined_term(buffer.paragraphs)
        return [_make_chunk(buffer, full_text, clause_no=None, defined_term=defined_term)]
    return _split_oversized_article(buffer, max_chars)


def _split_oversized_article(buffer: _ArticleBuffer, max_chars: int) -> list[LawChunk]:
    """긴 조문을 항(①②…) 단위로, 항이 없으면 호(1. 2. …) 단위로 나눠 Chunk를 만든다."""
    if _has_clause_markers(buffer.paragraphs):
        pattern, clause_label = _CLAUSE_PATTERN, lambda label: label
    else:
        pattern, clause_label = _ITEM_PATTERN, lambda label: f"{label}호"

    chunks = []
    for label, body_paragraphs in _split_by_pattern(buffer.paragraphs, pattern):
        text = _render_text(buffer, body_paragraphs)
        defined_term = _extract_defined_term(body_paragraphs)
        chunks.append(_make_chunk(buffer, text, clause_label(label), defined_term=defined_term))
    return chunks


def _has_clause_markers(paragraphs: list[str]) -> bool:
    """문단 중 항 기호(①~⑮)로 시작하는 것이 있는지 확인한다."""
    return any(_CLAUSE_PATTERN.match(p.strip()) for p in paragraphs)


def _split_by_pattern(paragraphs: list[str], pattern: re.Pattern) -> list[tuple[str, list[str]]]:
    """preamble(첫 마커 이전 문단)은 각 세그먼트 본문 앞에 반복 포함해, 분할된
    Chunk 각각이 맥락 없이도 읽히도록 한다."""
    preamble: list[str] = []
    segments: list[tuple[str, list[str]]] = []
    current_label: str | None = None
    current_body: list[str] = []

    for paragraph in paragraphs:
        match = pattern.match(paragraph.strip())
        if match:
            if current_label is not None:
                segments.append((current_label, current_body))
            current_label = match.group(1)
            current_body = [paragraph]
        elif current_label is None:
            preamble.append(paragraph)
        else:
            current_body.append(paragraph)

    if current_label is not None:
        segments.append((current_label, current_body))

    return [(label, preamble + body) for label, body in segments]


def format_article_label(article_no: int | str) -> str:
    """article_no("22의2" 등)를 올바른 법률 조문 표기("제22조의2")로 변환한다.

    주의: article_no가 "22의2"처럼 가지번호를 포함하는 문자열일 때
    f"제{article_no}조"로 단순 조립하면 "제22의2조"가 되어 틀린다 —
    "의N"은 "조" 뒤에 붙어야 한다.
    """
    if article_no == "부칙":
        return "부칙"
    text = str(article_no)
    main_no, _, branch_no = text.partition("의")
    return f"제{main_no}조의{branch_no}" if branch_no else f"제{main_no}조"


def _render_text(buffer: _ArticleBuffer, body_paragraphs: list[str]) -> str:
    """"제N조(제목)\\n본문" 형태의 Chunk 텍스트를 조립한다(부칙은 제목 없이 "부칙")."""
    label = format_article_label(buffer.article_no)
    heading = label if buffer.article_no == "부칙" else f"{label}({buffer.article_title})"
    body = "\n".join(body_paragraphs).strip()
    return f"{heading}\n{body}" if body else heading


def _extract_defined_term(paragraphs: list[str]) -> str | None:
    """본문에서 "“용어”란/이란" 패턴을 찾아 정의 대상 용어를 반환한다(없으면 None)."""
    for paragraph in paragraphs:
        match = _DEFINED_TERM_PATTERN.search(paragraph)
        if match:
            return match.group(1)
    return None


def _make_chunk(
    buffer: _ArticleBuffer, text: str, clause_no: str | None, defined_term: str | None = None
) -> LawChunk:
    """조/항 번호 기반 결정론적 UUIDv5 ID와 메타데이터를 붙여 LawChunk를 생성한다."""
    id_key = f"art-{buffer.article_no}" if clause_no is None else f"art-{buffer.article_no}-clause-{clause_no}"
    return LawChunk(
        id=str(uuid.uuid5(_CHUNK_ID_NAMESPACE, id_key)),
        text=text,
        chapter_no=buffer.chapter_no,
        chapter_title=buffer.chapter_title,
        article_no=buffer.article_no,
        article_title=buffer.article_title,
        clause_no=clause_no,
        defined_term=defined_term,
    )
