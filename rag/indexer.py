import argparse

from rag.loader import load_law_document
from rag.chunker import chunk_law_document
from rag.vectorstore import build_vectorstore

DEFAULT_DOCUMENT_PATH = "data/ai_basic_law.hwpx"


def run_indexing(path: str = DEFAULT_DOCUMENT_PATH) -> int:
    """hwpx 문서를 로딩ㆍChunking해 Qdrant에 색인하고 Chunk 수를 반환한다."""
    paragraphs = load_law_document(path)
    chunks = chunk_law_document(paragraphs)
    build_vectorstore(chunks)
    return len(chunks)


def main() -> None:
    """CLI 인자(--path)를 받아 색인을 실행하고 결과 Chunk 수를 출력한다."""
    parser = argparse.ArgumentParser(description="법령 문서 Offline 색인")
    parser.add_argument("--path", default=DEFAULT_DOCUMENT_PATH, help="색인할 hwpx 파일 경로")
    args = parser.parse_args()

    count = run_indexing(args.path)
    print(f"{count}개 Chunk 색인 완료")


if __name__ == "__main__":
    main()
