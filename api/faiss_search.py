import json
import logging
import os
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

FAISS_INDEX_DIR = os.path.join(settings.BASE_DIR, "faiss_index")
FAISS_INDEX_PATH = os.path.join(FAISS_INDEX_DIR, "tools.index")
FAISS_METADATA_PATH = os.path.join(FAISS_INDEX_DIR, "tools_metadata.json")
MODEL_NAME = "all-MiniLM-L6-v2"


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

            self.model = SentenceTransformer(MODEL_NAME)

    def load_index(self):
        if not os.path.exists(FAISS_INDEX_PATH) or not os.path.exists(
            FAISS_METADATA_PATH
        ):
            logger.warning("FAISS index files not found at %s", FAISS_INDEX_DIR)
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
            logger.error("Failed to load FAISS index: %s", e)
            return False

    def build_index(self):
        from api.models import Tool

        self._ensure_model()

        tools = Tool.objects.filter(is_active=True).values(
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

        tools_list = list(tools)
        if not tools_list:
            logger.warning("No active tools found to build FAISS index")
            return 0

        texts = []
        tool_ids = []
        tool_metadata = []

        for tool in tools_list:
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
            text = " ".join(filter(None, parts))
            texts.append(text)
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

        logger.info("Generating embeddings for %d tools...", len(texts))
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
            "FAISS index built and saved: %d tools, dimension=%d",
            len(tool_ids),
            dimension,
        )
        return len(tool_ids)

    def search(self, query, top_k=20, similarity_threshold=0.3):
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

        # Get tool IDs that match the similarity threshold
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

        # Fetch fresh data from database with all fields including rating
        from api.models import Tool
        from api.serializers import ToolListSerializer

        tools = Tool.objects.filter(
            id__in=matched_tool_ids, is_active=True
        ).prefetch_related("categories")
        serializer = ToolListSerializer(tools, many=True)
        results = serializer.data

        # Add similarity scores to results
        for result in results:
            result["similarity"] = similarity_scores.get(result["id"], 0)

        # Sort by similarity score (highest first)
        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)

        return results

    @property
    def is_loaded(self):
        return self._loaded

    @property
    def tool_count(self):
        return len(self.tool_ids) if self._loaded else 0
