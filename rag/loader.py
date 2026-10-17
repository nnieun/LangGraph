import re
import zipfile
from xml.etree import ElementTree

# hwpx는 zip 컨테이너이며 본문은 OWPML 네임스페이스의 Contents/section0.xml
# 안에 <hp:p>(문단) > <hp:run> > <hp:t>(텍스트) 구조로 들어 있다.
_HWPML_PARAGRAPH_TEXT_TAG = "{http://www.hancom.co.kr/hwpml/2011/paragraph}t"
_SECTION_XML_PATH = "Contents/section0.xml"
_CHAPTER_HEADING_PATTERN = re.compile(r"^제\d+장")


def load_law_document(path: str) -> list[str]:
    """hwpx를 읽어 문단(paragraph) 단위 텍스트 리스트를 반환한다."""
    paragraphs = _extract_paragraphs_from_hwpx(path)
    return _strip_front_matter(paragraphs)


def _extract_paragraphs_from_hwpx(path: str) -> list[str]:
    """hwpx의 section0.xml에서 비어 있지 않은 <hp:t> 텍스트를 순서대로 추출한다."""
    try:
        with zipfile.ZipFile(path) as archive:
            section_xml = archive.read(_SECTION_XML_PATH)
    except (zipfile.BadZipFile, KeyError) as error:
        raise ValueError(f"hwpx 파일을 읽을 수 없습니다: {path}") from error

    root = ElementTree.fromstring(section_xml)
    return [
        text_node.text
        for text_node in root.iter(_HWPML_PARAGRAPH_TEXT_TAG)
        if text_node.text
    ]


def _strip_front_matter(paragraphs: list[str]) -> list[str]:
    """법제처 로고/QR 설명/표지 캡션 등 '제1장' 등장 이전의 비본문 블록을 제거한다."""
    for index, paragraph in enumerate(paragraphs):
        if _CHAPTER_HEADING_PATTERN.match(paragraph.strip()):
            return paragraphs[index:]
    return paragraphs
