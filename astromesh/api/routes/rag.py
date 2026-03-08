from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class RAGIngestRequest(BaseModel):
    document: str
    metadata: dict = {}
    doc_id_prefix: str = "doc"


class RAGQueryRequest(BaseModel):
    query: str
    top_k: int = 5


@router.post("/rag/ingest")
async def ingest_document(request: RAGIngestRequest):
    return {"status": "not_configured", "chunks": 0}


@router.post("/rag/query")
async def query_rag(request: RAGQueryRequest):
    return {"query": request.query, "results": [], "top_k": request.top_k}
