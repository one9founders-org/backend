"""
FAISS Search Service — fixed version.

Key changes vs original:
  1. Index is persisted to / loaded from S3 so it survives deployments.
  2. Explicit logging replaces silent failures.
  3. Thread-safe singleton with double-checked locking (unchanged, kept correct).
  4. Embedding dimension (384) matches the sentence-transformer model used here.
     The pgvector field (1536) is a separate concern for pgvector-based search;
     FAISS uses its own local embeddings via all-MiniLM-L6-v2.
  5. build_index() is exposed as a management command target only — never called
     inside a web request.
"""

import json
import logging
import os
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

MODEL_NAME = "all-MiniLM-L6-v2"

# Local cache dir (ephemeral inside container — rebuilt from S3 on cold start)
FAISS_INDEX_DIR = os.path.join(settings.BASE_DIR, "faiss_index")
FAISS_INDEX_PATH = os.path.join(FAISS_INDEX_DIR, "tools.index")
FAISS_METADATA_PATH = os.path.join(FAISS_INDEX_DIR, "tools_metadata.json")

# S3 paths (persistent across deploys)
S3_INDEX_KEY = "faiss/tools.index"
S3_METADATA_KEY = "faiss/tools_metadata.json"


def _get_s3_client():
    import boto3

    return boto3.client(
        "s3",
        region_name=settings.AWS_S3_REGION_NAME,
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    )


def _faiss_bucket():
    """Bucket used to persist the FAISS index (decoupled from media bucket)."""
    return (
        getattr(settings, "S3_FAISS_BUCKET_NAME", None)
        or settings.AWS_STORAGE_BUCKET_NAME
    )


def _download_index_from_s3() -> bool:
    """Download FAISS index + metadata from S3 to local cache.

    Returns True on success.
    """
    try:
        s3 = _get_s3_client()
        bucket = _faiss_bucket()
        os.makedirs(FAISS_INDEX_DIR, exist_ok=True)

        s3.download_file(bucket, S3_INDEX_KEY, FAISS_INDEX_PATH)
        s3.download_file(bucket, S3_METADATA_KEY, FAISS_METADATA_PATH)
        logger.info("FAISS index downloaded from S3 successfully.")
        return True
    except Exception as e:
        logger.warning("Could not download FAISS index from S3: %s", e)
        return False


def _upload_index_to_s3() -> bool:
    """Upload freshly built FAISS index + metadata to S3. Returns True on success."""
    try:
        s3 = _get_s3_client()
        bucket = _faiss_bucket()

        s3.upload_file(FAISS_INDEX_PATH, bucket, S3_INDEX_KEY)
        s3.upload_file(FAISS_METADATA_PATH, bucket, S3_METADATA_KEY)
        logger.info("FAISS index uploaded to S3 successfully.")
        return True
    except Exception as e:
        logger.error("Failed to upload FAISS index to S3: %s", e)
        return False


class FAISSSearchService:
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self.index = None
        self.tool_ids = []
        self.tool_metadata = []
        self.model = None
        self._loaded = False

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_model(self):
        if self.model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading sentence-transformer model: %s", MODEL_NAME)
            self.model = SentenceTransformer(MODEL_NAME)

    def load_index(self) -> bool:
        """
        Load index from local cache. If not present, attempt download from S3.
        Returns True if index is ready.
        """
        # Try local cache first
        if not (
            os.path.exists(FAISS_INDEX_PATH) and os.path.exists(FAISS_METADATA_PATH)
        ):
            logger.info("Local FAISS index not found — attempting S3 download.")
            if not _download_index_from_s3():
                logger.warning(
                    "FAISS index unavailable locally and on S3. "
                    "Run: python manage.py build_faiss_index"
                )
                return False

        try:
            import faiss

            self.index = faiss.read_index(FAISS_INDEX_PATH)
            with open(FAISS_METADATA_PATH, "r") as f:
                metadata = json.load(f)

            self.tool_ids = metadata["tool_ids"]
            self.tool_metadata = metadata["tools"]
            self._loaded = True
            logger.info(
                "FAISS index loaded: %d tools, dimension=%d",
                len(self.tool_ids),
                self.index.d,
            )
            return True
        except Exception as e:
            logger.error("Failed to load FAISS index from disk: %s", e)
            return False

    def build_index(self, upload_to_s3: bool = True) -> int:
        """
        Build FAISS index from all active tools.
        Saves locally and, if upload_to_s3=True, pushes to S3.
        Returns count of indexed tools.
        """
        from api.models import Tool

        self._ensure_model()

        tools = list(
            Tool.objects.filter(is_active=True).values(
                "id",
                "name",
                "short_description",
                "description",
                "website",
                "logo_url",
                "slug",
                "tags",
                "use_cases",
                "features",
                "startup_benefits",
                "ideal_for",
            )
        )

        if not tools:
            logger.warning("No active tools found — FAISS index not built.")
            return 0

        texts = []
        tool_ids = []
        tool_metadata = []

        for tool in tools:
            parts = [
                tool["name"],
                tool["short_description"] or "",
                tool["description"] or "",
                " ".join(tool["tags"] or []),
                " ".join(tool["use_cases"] or []),
                " ".join(tool["features"] or []),
                tool["startup_benefits"] or "",
                " ".join(tool["ideal_for"] or []),
            ]
            texts.append(" ".join(filter(None, parts)))
            tool_ids.append(tool["id"])
            tool_metadata.append(
                {
                    "id": tool["id"],
                    "name": tool["name"],
                    "short_description": tool["short_description"] or "",
                    "description": tool["description"] or "",
                    "website": tool["website"] or "",
                    "logo_url": tool["logo_url"] or "",
                    "slug": tool["slug"] or "",
                }
            )

        import faiss
        import numpy as np

        logger.info("Generating FAISS embeddings for %d tools …", len(texts))
        embeddings = self.model.encode(
            texts, show_progress_bar=True, normalize_embeddings=True
        )
        embeddings = np.array(embeddings, dtype=np.float32)

        dimension = embeddings.shape[1]
        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings)

        os.makedirs(FAISS_INDEX_DIR, exist_ok=True)
        faiss.write_index(index, FAISS_INDEX_PATH)

        metadata = {
            "tool_ids": tool_ids,
            "tools": tool_metadata,
            "dimension": dimension,
            "model_name": MODEL_NAME,
            "total_tools": len(tool_ids),
        }
        with open(FAISS_METADATA_PATH, "w") as f:
            json.dump(metadata, f)

        self.index = index
        self.tool_ids = tool_ids
        self.tool_metadata = tool_metadata
        self._loaded = True

        logger.info(
            "FAISS index built: %d tools, dimension=%d", len(tool_ids), dimension
        )

        if upload_to_s3:
            _upload_index_to_s3()

        return len(tool_ids)

    def search(self, query: str, top_k: int = 20, similarity_threshold: float = 0.3):
        """Semantic search using FAISS.

        Returns serialized tool list with similarity scores,
        or None if index unavailable.
        """
        if not self._loaded:
            if not self.load_index():
                return None

        import numpy as np

        self._ensure_model()

        query_embedding = self.model.encode([query], normalize_embeddings=True)
        query_embedding = np.array(query_embedding, dtype=np.float32)

        scores, indices = self.index.search(
            query_embedding, min(top_k, len(self.tool_ids))
        )

        matched_tool_ids = []
        similarity_scores = {}
        for score, idx in zip(scores[0], indices[0]):
            if idx == -1:
                continue
            similarity = float(score)
            if similarity < similarity_threshold:
                continue
            tool_id = self.tool_ids[idx]
            matched_tool_ids.append(tool_id)
            similarity_scores[tool_id] = round(similarity, 4)

        if not matched_tool_ids:
            return []

        from api.models import Tool
        from api.serializers import ToolListSerializer

        tools = Tool.objects.filter(
            id__in=matched_tool_ids, is_active=True
        ).prefetch_related("categories")

        results = list(ToolListSerializer(tools, many=True).data)
        for result in results:
            result["similarity"] = similarity_scores.get(result["id"], 0)
        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results

    @property
    def is_loaded(self):
        return self._loaded

    @property
    def tool_count(self):
        return len(self.tool_ids) if self._loaded else 0
