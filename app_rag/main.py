from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from common.qdrant import get_qdrant_client
from rag import pipeline

app = FastAPI()


class AskRequest(BaseModel):
    question: str


class Source(BaseModel):
    article: str
    content: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]


@app.get("/")
def root():
    return {
        "message": "RAG API"
    }


@app.get("/health")
def health() -> JSONResponse:
    try:
        get_qdrant_client().get_collections()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded"})
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    try:
        result = pipeline.answer_question(request.question)
    except Exception as error:
        raise HTTPException(status_code=500, detail="internal error") from error

    return AskResponse(
        answer=result.answer,
        sources=[Source(article=s.article, content=s.content) for s in result.sources],
    )
