"""RAGAS Evaluation - Evaluate RAG system using RAGAS metrics."""

import asyncio
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import get_settings
from app.database.neo4j_client import Neo4jClient
from app.database.milvus_client import MilvusClient
from app.rag.embeddings import EmbeddingService
from app.rag.bm25_retriever import BM25Retriever
from app.rag.hyde import HyDEGenerator
from app.rag.hybrid_retriever import HybridRetriever
from app.rag.query_rewriter import QueryRewriter
from app.qa.entity_linker import EntityLinker
from app.qa.subgraph_retriever import SubgraphRetriever
from app.qa.answer_generator import AnswerGenerator
from app.qa.pipeline import QAPipeline
from app.eval.dataset import load_kgclue_dataset, EvalSample

# RAGAS imports
from ragas import evaluate
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)
from datasets import Dataset
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

KGCLUE_PATH = "/mnt/e/hermes_code_workspace/dataset/通用百科数据集/KgCLUE/datasets/test_public.json"


async def build_pipeline() -> tuple[QAPipeline, Neo4jClient]:
    """Initialize the full QA pipeline for evaluation."""
    settings = get_settings()

    # Neo4j
    neo4j = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_password)
    await neo4j.connect()

    # Milvus
    milvus = MilvusClient(host=settings.milvus_host, port=settings.milvus_port)

    # Embedding
    embedding = EmbeddingService(base_url=settings.embedding_base_url, model=settings.embedding_model)

    # HyDE
    hyde = HyDEGenerator(settings.llm_model_name, settings.llm_base_url, settings.llm_api_key)

    # BM25
    bm25 = BM25Retriever()
    try:
        docs = milvus.load_all_docs(settings.milvus_collection)
        bm25.build_index(docs)
    except Exception:
        pass

    # Query Rewriter
    query_rewriter = QueryRewriter(settings.llm_model_name, settings.llm_base_url, settings.llm_api_key)

    # Entity Linker
    entity_linker = EntityLinker()
    try:
        result = await neo4j.execute(
            "MATCH (n:Entity {source: 'ownthink'}) RETURN n.name AS name LIMIT 10000"
        )
        entity_names = [r["name"] for r in result if r.get("name")]
        entity_linker.load_from_neo4j(entity_names)
    except Exception:
        pass

    # Graph Retriever
    graph_retriever = SubgraphRetriever(neo4j)

    # Hybrid Retriever
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

    # Answer Generator
    generator = AnswerGenerator(settings.llm_model_name, settings.llm_base_url, settings.llm_api_key)

    # Pipeline
    pipeline = QAPipeline(retriever, generator)
    return pipeline, neo4j


def get_llm_for_ragas():
    """Get LLM instance configured for RAGAS evaluation."""
    settings = get_settings()
    return ChatOpenAI(
        model=settings.llm_model_name,
        openai_api_base=settings.llm_base_url,
        openai_api_key=settings.llm_api_key,
        temperature=0,
    )


def get_embeddings_for_ragas():
    """Get Embeddings instance configured for RAGAS evaluation."""
    settings = get_settings()
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        openai_api_base=settings.embedding_base_url,
        openai_api_key="ollama",  # Ollama doesn't need a real key
    )


async def collect_ragas_data(
    pipeline: QAPipeline,
    samples: list[EvalSample],
    entity_names: set[str],
) -> Dataset:
    """Collect data for RAGAS evaluation."""
    questions = []
    answers = []
    contexts_list = []
    ground_truths = []

    for i, sample in enumerate(samples):
        try:
            # Run pipeline
            result = await pipeline.answer(sample.question)

            # Collect data
            questions.append(sample.question)
            answers.append(result.answer)

            # Format contexts as list of strings
            contexts = []
            if hasattr(result, 'contexts') and result.contexts:
                contexts = result.contexts
            elif hasattr(result, 'retrieved_docs') and result.retrieved_docs:
                contexts = [doc.get('content', str(doc)) for doc in result.retrieved_docs]
            contexts_list.append(contexts)

            ground_truths.append(sample.reference_answer)

            print(f"  [{i+1}/{len(samples)}] Collected: {sample.question[:40]}...")

        except Exception as e:
            print(f"  [{i+1}/{len(samples)}] ERROR: {e}")
            continue

    # Create HuggingFace Dataset
    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,
    })

    return dataset


async def main():
    """Run RAGAS evaluation."""
    print("=" * 60)
    print("RAGAS Evaluation - History KG-QA")
    print("=" * 60)

    # Build pipeline
    print("\n[1/4] Building pipeline...")
    pipeline, neo4j = await build_pipeline()

    # Load entity names
    print("[2/4] Loading entity names from Neo4j...")
    result = await neo4j.execute(
        "MATCH (n:Entity {source: 'ownthink'}) RETURN n.name AS name"
    )
    entity_names = {r["name"] for r in result if r.get("name")}
    print(f"  Loaded {len(entity_names)} entity names")

    # Load evaluation dataset
    print("[3/4] Loading KgCLUE evaluation dataset...")
    samples = load_kgclue_dataset(KGCLUE_PATH, entity_names, max_samples=30)
    print(f"  Loaded {len(samples)} evaluation samples")

    if not samples:
        print("  No matching samples found. Exiting.")
        await neo4j.close()
        return

    # Collect data for RAGAS
    print(f"[4/4] Collecting data for RAGAS evaluation...")
    dataset = await collect_ragas_data(pipeline, samples, entity_names)

    if len(dataset) == 0:
        print("  No data collected. Exiting.")
        await neo4j.close()
        return

    print(f"\n  Collected {len(dataset)} samples for evaluation")

    # Get LLM and Embeddings for RAGAS
    llm = get_llm_for_ragas()
    embeddings = get_embeddings_for_ragas()

    # Run RAGAS evaluation
    print("\nRunning RAGAS evaluation...")
    try:
        result = evaluate(
            dataset=dataset,
            metrics=[
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            ],
            llm=llm,
            embeddings=embeddings,
        )

        # Print results
        print("\n" + "=" * 60)
        print("RAGAS RESULTS")
        print("=" * 60)
        print(result)

        # Save results
        output_path = Path(__file__).parent / "ragas_eval_results.json"
        results_dict = {
            "metrics": {
                "answer_relevancy": result["answer_relevancy"],
                "context_precision": result["context_precision"],
                "context_recall": result["context_recall"],
                "faithfulness": result["faithfulness"],
            },
            "samples": len(dataset),
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(results_dict, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {output_path}")

    except Exception as e:
        print(f"\nRAGAS evaluation failed: {e}")
        import traceback
        traceback.print_exc()

    await neo4j.close()


if __name__ == "__main__":
    asyncio.run(main())
