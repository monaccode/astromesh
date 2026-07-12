from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from astromesh.rag.factory import build_pipeline
from astromesh.rag.loader import RAGPipelineLoader
from astromesh.rag.pipeline import RAGPipeline, result_to_list

router = APIRouter()

_CONFIG_RAG_DIR = "./config/rag"

_PIPELINE_CACHE: dict[str, RAGPipeline] = {}


def resolve_pipeline(name: str) -> RAGPipeline | None:
    """Resolve a RAGPipeline by name from config/rag. Overridable in tests.

    Memoized per name so ingest/query requests share the same pipeline
    instance (in-memory backends like faiss lose data otherwise).
    """
    if name in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[name]
    spec = RAGPipelineLoader(_CONFIG_RAG_DIR).load_all().get(name)
    if spec is None:
        return None
    pipeline = build_pipeline(spec)
    _PIPELINE_CACHE[name] = pipeline
    return pipeline


class RAGIngestRequest(BaseModel):
    pipeline: str
    document: str
    metadata: dict = {}
    doc_id_prefix: str = "doc"


class RAGQueryRequest(BaseModel):
    pipeline: str
    query: str
    top_k: int = 5


@router.post("/rag/ingest")
async def ingest_document(request: RAGIngestRequest):
    pipeline = resolve_pipeline(request.pipeline)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"RAGPipeline not found: {request.pipeline}")
    n = await pipeline.ingest(
        request.document, metadata=request.metadata, doc_id_prefix=request.doc_id_prefix
    )
    return {"pipeline": request.pipeline, "chunks": n}


@router.post("/rag/query")
async def query_rag(request: RAGQueryRequest):
    pipeline = resolve_pipeline(request.pipeline)
    if pipeline is None:
        raise HTTPException(status_code=404, detail=f"RAGPipeline not found: {request.pipeline}")
    raw = await pipeline.query(request.query, top_k=request.top_k)
    return {"query": request.query, "results": result_to_list(raw), "top_k": request.top_k}
