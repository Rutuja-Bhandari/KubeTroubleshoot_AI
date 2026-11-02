
from pathlib import Path

import chromadb

from langchain_community.document_loaders import (
    DirectoryLoader,
    TextLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base"
CHROMA_DIR = PROJECT_ROOT / "chroma_db"

COLLECTION_NAME = "kube_troubleshoot_knowledge"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

EXPECTED_RUNBOOKS = {
    "OOMKilled.md",
    "CrashLoopBackOff.md",
    "ImagePullBackOff.md",
    "PendingPods.md",
    "ProbeFailures.md",
    "CreateContainerConfigError.md",
    "VolumeMountFailures.md"
}


def load_documents():
    if not KNOWLEDGE_BASE.exists():
        raise FileNotFoundError(
            f"Knowledge base directory not found: {KNOWLEDGE_BASE}"
        )

    loader = DirectoryLoader(
        str(KNOWLEDGE_BASE),
        glob="**/*.md",
        loader_cls=TextLoader,
        loader_kwargs={"encoding": "utf-8"},
        show_progress=True,
        silent_errors=False
    )

    documents = loader.load()

    for document in documents:
        source = Path(document.metadata["source"]).resolve()

        try:
            document.metadata["source"] = str(
                source.relative_to(PROJECT_ROOT)
            )
        except ValueError:
            document.metadata["source"] = str(source)

        document.metadata["filename"] = source.name

    return documents


def validate_documents(documents):
    found_runbooks = {
        document.metadata.get("filename")
        for document in documents
    }

    missing_runbooks = EXPECTED_RUNBOOKS - found_runbooks

    print(f"Markdown documents found: {len(found_runbooks)}")

    if missing_runbooks:
        print("\nExpected runbooks not found:")
        for filename in sorted(missing_runbooks):
            print(f"- {filename}")

    if not documents:
        raise ValueError(
            f"No Markdown documents found in {KNOWLEDGE_BASE}"
        )

    return found_runbooks


def split_documents(documents):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=150,
        add_start_index=True
    )

    return splitter.split_documents(documents)


def create_vector_database(chunks):
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR)
    )

    existing_collections = {
        collection.name
        for collection in client.list_collections()
    }

    if COLLECTION_NAME in existing_collections:
        client.delete_collection(name=COLLECTION_NAME)
        print("Existing knowledge collection removed.")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL
    )

    vector_db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_DIR)
    )

    return vector_db


def main():
    print("=" * 45)
    print("KubeTroubleshoot AI - RAG Ingestion")
    print("=" * 45)

    print("\nLoading Markdown documents...")
    documents = load_documents()

    found_runbooks = validate_documents(documents)

    print(f"\nDocuments loaded: {len(documents)}")
    print(f"Expected runbooks found: {len(EXPECTED_RUNBOOKS & found_runbooks)}/7")

    print("\nSplitting documents...")
    chunks = split_documents(documents)
    print(f"Chunks created: {len(chunks)}")

    if not chunks:
        raise ValueError("No chunks were created from the Markdown documents.")

    print("\nCreating embeddings and rebuilding collection...")
    vector_db = create_vector_database(chunks)

    print(f"Chunks stored: {vector_db._collection.count()}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Vector database: {CHROMA_DIR}")
    print("\nRAG ingestion completed successfully.")


if __name__ == "__main__":
    main()






# from pathlib import Path

# from langchain_community.document_loaders import (
#     DirectoryLoader,
#     TextLoader
# )

# from langchain_text_splitters import (
#     RecursiveCharacterTextSplitter
# )

# from langchain_community.embeddings import (
#     HuggingFaceEmbeddings
# )

# from langchain_community.vectorstores import Chroma


# # Project root
# PROJECT_ROOT = Path(__file__).resolve().parents[2]

# # Knowledge base directory
# KNOWLEDGE_BASE = PROJECT_ROOT / "knowledge_base"

# # Chroma database directory
# CHROMA_DIR = PROJECT_ROOT / "chroma_db"


# def load_documents():

#     documents = []

#     folders = [
#         KNOWLEDGE_BASE / "runbooks",
#         KNOWLEDGE_BASE / "incidents",
#         KNOWLEDGE_BASE / "kubernetes_docs"
#     ]

#     for folder in folders:

#         loader = DirectoryLoader(
#             str(folder),
#             glob="**/*.md",
#             loader_cls=TextLoader,
#             loader_kwargs={
#                 "encoding": "utf-8"
#             }
#         )

#         folder_documents = loader.load()

#         documents.extend(folder_documents)

#     return documents


# def split_documents(documents):

#     splitter = RecursiveCharacterTextSplitter(
#         chunk_size=800,
#         chunk_overlap=150
#     )

#     return splitter.split_documents(documents)


# def create_vector_database(chunks):

#     embeddings = HuggingFaceEmbeddings(
#         model_name="sentence-transformers/all-MiniLM-L6-v2"
#     )

#     vector_db = Chroma.from_documents(
#         documents=chunks,
#         embedding=embeddings,
#         persist_directory=str(CHROMA_DIR)
#     )

#     return vector_db


# def main():

#     print("====================================")
#     print("KubeTroubleshoot AI - RAG Ingestion")
#     print("====================================")

#     print("\nLoading documents...")

#     documents = load_documents()

#     print(f"Documents loaded: {len(documents)}")

#     if not documents:
#         print("No documents found.")
#         return

#     print("\nSplitting documents...")

#     chunks = split_documents(documents)

#     print(f"Chunks created: {len(chunks)}")

#     print("\nCreating embeddings and vector database...")

#     create_vector_database(chunks)

#     print("\nRAG ingestion completed successfully.")

#     print(f"Vector database: {CHROMA_DIR}")


# if __name__ == "__main__":
#     main()