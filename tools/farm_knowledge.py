"""
Farm knowledge RAG tool.

Loads the farm operations knowledge base (distinct from the veterinary
knowledge base) and exposes it as an ADK FunctionTool.

Requires these three files in the data/ directory (download them from your
Colab session -- they are NOT the same files as the veterinary ones):
    data/farm_manager_config.json
    data/farm_manager_metadata.pkl
    data/farm_manager_index.faiss
"""

import json
import pickle
import faiss
from sentence_transformers import SentenceTransformer
from google.adk.tools import FunctionTool

CONFIG_PATH = "data/farm_manager_config.json"
METADATA_PATH = "data/farm_manager_metadata.pkl"
INDEX_PATH = "data/farm_manager_index.faiss"

with open(CONFIG_PATH, "r") as f:
    _config = json.load(f)

with open(METADATA_PATH, "rb") as f:
    _metadata = pickle.load(f)

_index = faiss.read_index(INDEX_PATH)

_embedding_model = SentenceTransformer(_config["embedding_model"])


def query_farm_knowledge(query: str, top_k: int = 3):
    """
    Query the poultry farm knowledge base for relevant information.

    Use this tool when the farmer asks general questions about:
    - Poultry farming practices
    - Farm management principles
    - Breed information
    - Housing, feeding, or egg production
    - Farm operations or biosecurity
    - Any poultry-related knowledge

    Args:
        query: The question or search query from the farmer
        top_k: Number of results to return (default: 3)

    Returns:
        Dictionary with search results or error message
    """
    if top_k is None or top_k <= 0:
        top_k = _config["top_k"]

    query_embedding = _embedding_model.encode([query], normalize_embeddings=True)
    distances, indices = _index.search(query_embedding, top_k)

    results = []
    for idx, distance in zip(indices[0], distances[0]):
        if idx >= 0 and idx < len(_metadata):
            chunk_metadata = _metadata[idx]
            results.append({
                "category_id": chunk_metadata.get("category_id", idx + 1),
                "category": chunk_metadata.get("title", f"Category {idx + 1}"),
                "content": chunk_metadata.get("content", ""),
                "relevance_score": float(distance),
                "sections": chunk_metadata.get("sections", []),
            })

    if not results:
        return {
            "found": False,
            "query": query,
            "message": "No relevant information found in the knowledge base.",
        }

    return {
        "found": True,
        "query": query,
        "results": results,
        "total_results": len(results),
    }


farm_knowledge_tool = FunctionTool(query_farm_knowledge)
