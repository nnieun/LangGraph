from dataclasses import asdict

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from common.ai_model import get_embedding_model
from common.config import QDRANT_COLLECTION
from common.qdrant import get_qdrant_client
from rag.chunker import LawChunk


def build_vectorstore(chunks: list[LawChunk]) -> None:
    """Chunk 텍스트를 Embedding으로 변환해 Qdrant Collection에 upsert한다."""
    client = get_qdrant_client()
    embedding_model = get_embedding_model()

    vectors = embedding_model.embed_documents([chunk.text for chunk in chunks])
    ensure_collection(client, QDRANT_COLLECTION, vector_size=len(vectors[0]))

    points = [
        PointStruct(id=chunk.id, vector=vector, payload=asdict(chunk))
        for chunk, vector in zip(chunks, vectors)
    ]
    client.upsert(collection_name=QDRANT_COLLECTION, points=points)


def ensure_collection(client: QdrantClient, name: str, vector_size: int) -> None:
    """Collection이 없으면 지정된 벡터 차원으로 생성한다."""
    if client.collection_exists(name):
        return
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
