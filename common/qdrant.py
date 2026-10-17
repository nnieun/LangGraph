from qdrant_client import QdrantClient

from common.config import QDRANT_API_KEY, QDRANT_URL

def get_qdrant_client():
    # 잘못 입력된 `QDRANT_URL=QDRANT_URL=...` 형태를 방어하고 공백 제거
    url = QDRANT_URL.strip()
    while url.startswith("QDRANT_URL="):
        url = url.removeprefix("QDRANT_URL=").strip()

    return QdrantClient(
        url=url,
        api_key=QDRANT_API_KEY,
    )
