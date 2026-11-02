
from functools import lru_cache
from pathlib import Path

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHROMA_DIR = PROJECT_ROOT / "chroma_db"

COLLECTION_NAME = "kube_troubleshoot_knowledge"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embeddings():
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )


@lru_cache(maxsize=1)
def get_vector_database():
    if not CHROMA_DIR.exists():
        raise FileNotFoundError(
            f"Vector database not found: {CHROMA_DIR}. "
            "Run ai/rag/ingest.py first."
        )

    vector_db = Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_DIR),
        embedding_function=get_embeddings()
    )

    if vector_db._collection.count() == 0:
        raise ValueError(
            "The knowledge collection is empty. "
            "Run ai/rag/ingest.py to index the runbooks."
        )

    return vector_db


def search_knowledge_base(query, top_k=3):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must not be empty.")

    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be a positive integer.")

    vector_db = get_vector_database()

    return vector_db.similarity_search(
        query.strip(),
        k=top_k
    )


def search_knowledge_base_with_scores(query, top_k=3):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must not be empty.")

    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise ValueError("top_k must be a positive integer.")

    vector_db = get_vector_database()

    return vector_db.similarity_search_with_score(
        query.strip(),
        k=top_k
    )






# from pathlib import Path

# from langchain_community.embeddings import (
#     HuggingFaceEmbeddings
# )

# from langchain_community.vectorstores import Chroma


# PROJECT_ROOT = Path(__file__).resolve().parents[2]

# CHROMA_DIR = PROJECT_ROOT / "chroma_db"


# def get_vector_database():

#     embeddings = HuggingFaceEmbeddings(
#         model_name="sentence-transformers/all-MiniLM-L6-v2"
#     )

#     vector_db = Chroma(
#         persist_directory=str(CHROMA_DIR),
#         embedding_function=embeddings
#     )

#     return vector_db


# def search_knowledge_base(
#     query,
#     top_k=3
# ):

#     vector_db = get_vector_database()

#     results = vector_db.similarity_search(
#         query,
#         k=top_k
#     )

#     return results