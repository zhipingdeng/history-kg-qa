from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.config import get_settings
from app.database.neo4j_client import Neo4jClient
from app.database.milvus_client import MilvusClient
from app.database.mysql import get_engine, Base
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.qa import router as qa_router
from app.api.v1.knowledge import router as knowledge_router
from app.rag.embeddings import EmbeddingService
from app.rag.bm25_retriever import BM25Retriever
from app.rag.hyde import HyDEGenerator
from app.rag.query_rewriter import QueryRewriter
from app.rag.hybrid_retriever import HybridRetriever
from app.qa.entity_linker import EntityLinker
from app.qa.subgraph_retriever import SubgraphRetriever
from app.qa.answer_generator import AnswerGenerator
from app.qa.pipeline import QAPipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print("==> Starting lifespan initialization...", flush=True)

    # MySQL tables
    print("==> Creating MySQL tables...", flush=True)
    engine = get_engine(
        host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password,
        database=settings.mysql_database,
    )
    Base.metadata.create_all(bind=engine)
    print("  MySQL tables created.", flush=True)

    # Neo4j
    print("==> Connecting to Neo4j...", flush=True)
    neo4j = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    await neo4j.connect()
    app.state.neo4j = neo4j
    print("  Neo4j connected.", flush=True)

    # Milvus (optional - may fail, system will degrade gracefully)
    print("==> Connecting to Milvus...", flush=True)
    milvus = MilvusClient(host=settings.milvus_host, port=settings.milvus_port, max_retries=3)
    if milvus.connected:
        print("  Milvus connected.", flush=True)
    else:
        print("  Milvus unavailable - running in degraded mode (BM25 + Graph only).", flush=True)

    # Embedding
    print("==> Initializing Embedding service...", flush=True)
    embedding = EmbeddingService(
        base_url=settings.embedding_base_url,
        model=settings.embedding_model,
    )
    print("  Embedding service ready.", flush=True)

    # HyDE
    print("==> Initializing HyDE generator...", flush=True)
    hyde = HyDEGenerator(
        settings.llm_model_name,
        settings.llm_base_url,
        settings.llm_api_key,
    )
    print("  HyDE generator ready.", flush=True)

    # BM25: load documents from Milvus collection or Neo4j
    print("==> Loading BM25 index...", flush=True)
    bm25 = BM25Retriever()
    docs = []
    if milvus.connected:
        try:
            docs = milvus.load_all_docs(settings.milvus_collection)
            print(f"  BM25 index loaded with {len(docs)} documents from Milvus.", flush=True)
        except Exception as e:
            print(f"  BM25 index loading from Milvus failed: {e}", flush=True)

    if not docs:
        # Fallback: load entities from Neo4j for BM25
        try:
            result = await neo4j.execute(
                "MATCH (n:Entity) RETURN n.name AS name, n.value AS value LIMIT 10000"
            )
            docs = [
                {"text": f"{r['name']}: {r.get('value', '')}", "entity_name": r["name"], "source": "neo4j"}
                for r in result if r.get("name")
            ]
            print(f"  BM25 index loaded with {len(docs)} documents from Neo4j.", flush=True)
        except Exception as e:
            print(f"  BM25 index loading from Neo4j failed: {e}", flush=True)

    bm25.build_index(docs)

    # Query Rewriter
    print("==> Initializing Query Rewriter...", flush=True)
    query_rewriter = QueryRewriter(
        settings.llm_model_name,
        settings.llm_base_url,
        settings.llm_api_key,
    )
    print("  Query Rewriter ready.", flush=True)

    # Entity Linker + Graph Retriever
    print("==> Loading entity linker...", flush=True)
    entity_linker = EntityLinker()
    graph_retriever = SubgraphRetriever(neo4j)

    # Load known entities for entity linker
    try:
        result = await neo4j.execute(
            "MATCH (n:Entity) RETURN n.name AS name LIMIT 10000"
        )
        entity_names = [r["name"] for r in result if r.get("name")]
        entity_linker.load_from_neo4j(entity_names)
        print(f"  Entity linker loaded with {len(entity_names)} entities.", flush=True)
    except Exception as e:
        print(f"  Entity linker loading failed: {e}", flush=True)

    # Hybrid Retriever (vector + BM25 + HyDE + graph)
    print("==> Initializing Hybrid Retriever...", flush=True)
    retriever = HybridRetriever(
        milvus=milvus,
        embedding=embedding,
        bm25=bm25,
        hyde=hyde,
        collection=settings.milvus_collection,
        query_rewriter=query_rewriter,
        graph_retriever=graph_retriever,
        entity_linker=entity_linker,
    )
    print("  Hybrid Retriever ready.", flush=True)

    # Answer Generator
    print("==> Initializing Answer Generator...", flush=True)
    generator = AnswerGenerator(
        settings.llm_model_name,
        settings.llm_base_url,
        settings.llm_api_key,
    )
    print("  Answer Generator ready.", flush=True)

    # Pipeline
    app.state.qa_pipeline = QAPipeline(retriever, generator)
    print("==> QA Pipeline initialized successfully!", flush=True)

    yield

    await neo4j.close()


app = FastAPI(title="General KG-QA", version="0.1.0", lifespan=lifespan)
app.include_router(health_router, prefix="/api/v1", tags=["health"])
app.include_router(auth_router, prefix="/api/v1", tags=["auth"])
app.include_router(qa_router, prefix="/api/v1", tags=["qa"])
app.include_router(knowledge_router, prefix="/api/v1", tags=["knowledge"])
