import os

from dotenv import load_dotenv

load_dotenv(override=True)

LLM_API_KEY = os.getenv("LLM_API_KEY")
BASE_URL = os.getenv("LLM_BASE_URL")

MODEL = os.getenv("LLM_MODEL", "gpt-5.4-mini")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 2))
MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 2086))

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY") or None
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "ai_basic_law")

RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", 10))
RERANK_TOP_N = int(os.getenv("RERANK_TOP_N", 4))
CHUNK_MAX_CHARS = int(os.getenv("CHUNK_MAX_CHARS", 1500))

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "ragdb")
