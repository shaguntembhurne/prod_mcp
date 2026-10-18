#!/usr/bin/env python3
"""
Semantic search functionality using all-MiniLM-L6-v2 and FAISS.
"""

import pickle
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

from config_loader import get_config


class SemanticSearchConfig:
    """Configuration for semantic search."""

    def __init__(
        self,
        model_name: Optional[str] = None,
        model_cache_dir: Optional[str] = None,
        title_weight: Optional[int] = None,
        min_similarity_score: Optional[float] = None,
        cache_embeddings: Optional[bool] = None,
        show_progress: Optional[bool] = None,
    ):
        # Load from config file, with parameter overrides
        config = get_config()

        self.model_name = model_name or config.get("semantic_search", "model_name")

        # Set model cache directory to project's models folder
        if model_cache_dir is None:
            self.model_cache_dir = str(Path(__file__).parent / "models")
        else:
            self.model_cache_dir = model_cache_dir

        self.title_weight = title_weight or config.get("semantic_search", "title_weight")
        self.min_similarity_score = min_similarity_score or config.get("semantic_search", "min_similarity_score")
        self.cache_embeddings = (
            cache_embeddings if cache_embeddings is not None else config.get("semantic_search", "cache_embeddings")
        )
        self.show_progress = (
            show_progress if show_progress is not None else config.get("semantic_search", "show_progress")
        )


class DatasetSemanticSearch:
    """Semantic search for datasets using embeddings and FAISS."""

    def __init__(self, config: Optional[SemanticSearchConfig] = None):
        """Initialize the semantic search with the specified configuration."""
        self.config = config or SemanticSearchConfig()
        self.model = None
        self.index = None
        self.dataset_metadata = []

        # Ensure model cache directory exists
        os.makedirs(self.config.model_cache_dir, exist_ok=True)

        # File paths for caching
        self.embeddings_path = Path(__file__).parent / "data" / "embeddings.pkl"
        self.index_path = Path(__file__).parent / "data" / "faiss_index.bin"
        self.metadata_path = Path(__file__).parent / "data" / "metadata.pkl"

    def preload_model(self) -> None:
        """Preload the sentence transformer model to local directory."""
        if self.config.show_progress:
            print("🔄 Loading sentence transformer model...", file=sys.stderr, flush=True)

        # Set environment variable to use our local cache
        os.environ["TRANSFORMERS_CACHE"] = self.config.model_cache_dir
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = self.config.model_cache_dir

        # Load model with local cache directory
        self.model = SentenceTransformer(self.config.model_name, cache_folder=self.config.model_cache_dir)

        if self.config.show_progress:
            print(f"✅ Model loaded successfully to {self.config.model_cache_dir}", file=sys.stderr, flush=True)

    def _create_searchable_text(self, dataset: Dict[str, Any]) -> str:
        """
        Create searchable text from dataset metadata.
        Prioritizes title over ministry and sector based on configuration.
        """
        title = dataset.get("title", "")
        ministry = dataset.get("ministry", "")
        sector = dataset.get("sector", "")

        # Title gets weight by repeating it
        # This ensures title matches are prioritized in semantic search
        searchable_parts = [title] * self.config.title_weight + [ministry, sector]

        return " ".join(filter(None, searchable_parts))

    def build_embeddings(self, dataset_registry: List[Dict[str, Any]]) -> None:
        """Build and save embeddings for the dataset registry."""
        if not self.model:
            self.preload_model()

        if self.config.show_progress:
            print("🔄 Building embeddings for dataset registry...", file=sys.stderr, flush=True)

        # Create searchable texts
        searchable_texts = []
        for dataset in dataset_registry:
            searchable_text = self._create_searchable_text(dataset)
            searchable_texts.append(searchable_text)

        # Generate embeddings
        embeddings = self.model.encode(searchable_texts, show_progress_bar=self.config.show_progress)

        # Create FAISS index
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)  # Inner product for cosine similarity

        # Normalize embeddings for cosine similarity
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings.astype(np.float32))

        # Store metadata
        self.dataset_metadata = dataset_registry

        # Save to disk if caching is enabled
        if self.config.cache_embeddings:
            self._save_embeddings_and_index(embeddings)

        if self.config.show_progress:
            print(f"✅ Built and saved embeddings for {len(dataset_registry)} datasets", file=sys.stderr, flush=True)
        if self.config.show_progress:
            print(f"✅ Built and saved embeddings for {len(dataset_registry)} datasets", flush=True)

    def _save_embeddings_and_index(self, embeddings: np.ndarray) -> None:
        """Save embeddings, FAISS index, and metadata to disk."""
        # Ensure data directory exists
        self.embeddings_path.parent.mkdir(exist_ok=True)

        # Save embeddings
        with open(self.embeddings_path, "wb") as f:
            pickle.dump(embeddings, f)

        # Save FAISS index
        faiss.write_index(self.index, str(self.index_path))

        # Save metadata
        with open(self.metadata_path, "wb") as f:
            pickle.dump(self.dataset_metadata, f)

    def load_embeddings_and_index(self) -> bool:
        """Load precomputed embeddings and FAISS index from disk."""
        try:
            if not all(path.exists() for path in [self.embeddings_path, self.index_path, self.metadata_path]):
                return False

            if self.config.show_progress:
                print("🔄 Loading precomputed embeddings and index...", file=sys.stderr, flush=True)

            # Load FAISS index
            self.index = faiss.read_index(str(self.index_path))

            # Load metadata
            with open(self.metadata_path, "rb") as f:
                self.dataset_metadata = pickle.load(f)

            if self.config.show_progress:
                print(f"✅ Loaded embeddings for {len(self.dataset_metadata)} datasets", file=sys.stderr, flush=True)
            return True

        except Exception as e:
            if self.config.show_progress:
                print(f"⚠️ Error loading embeddings: {e}", file=sys.stderr, flush=True)
            return False

    def search(self, query: str, limit: int = 10, min_score: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Perform semantic search on the dataset registry.

        Args:
            query: Search query
            limit: Maximum number of results to return
            min_score: Minimum similarity score threshold (uses config default if None)

        Returns:
            List of matching datasets with metadata and similarity scores
        """
        if not self.model:
            self.preload_model()

        if not self.index or not self.dataset_metadata:
            raise ValueError("Embeddings not loaded. Call load_embeddings_and_index() or build_embeddings() first.")

        # Use config default if min_score not provided
        if min_score is None:
            min_score = self.config.min_similarity_score

        # Encode the query
        query_embedding = self.model.encode([query])
        faiss.normalize_L2(query_embedding)

        # Search in FAISS index
        scores, indices = self.index.search(query_embedding.astype(np.float32), limit)

        # Filter results by minimum score and prepare response
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if score >= min_score and idx < len(self.dataset_metadata):
                dataset = self.dataset_metadata[idx]
                result = {
                    "resource_id": dataset["resource_id"],
                    "title": dataset["title"],
                    "ministry": dataset.get("ministry", "Unknown"),
                    "sector": dataset.get("sector", "Unknown"),
                    "similarity_score": float(score),
                    "metadata": dataset,  # Include full metadata for LLM context
                }
                results.append(result)

        return results

    def is_ready(self) -> bool:
        """Check if the semantic search is ready to use."""
        return self.model is not None and self.index is not None and len(self.dataset_metadata) > 0


def initialize_semantic_search(
    dataset_registry: List[Dict[str, Any]], force_rebuild: bool = False, config: Optional[SemanticSearchConfig] = None
) -> DatasetSemanticSearch:
    """
    Initialize semantic search with the dataset registry.

    Args:
        dataset_registry: List of dataset metadata
        force_rebuild: Whether to force rebuilding embeddings even if they exist
        config: Configuration for semantic search (uses defaults if None)

    Returns:
        Initialized DatasetSemanticSearch instance
    """
    search_engine = DatasetSemanticSearch(config)

    # Preload the model first
    search_engine.preload_model()

    # Try to load existing embeddings if caching is enabled
    if not force_rebuild and search_engine.config.cache_embeddings and search_engine.load_embeddings_and_index():
        # Verify the loaded data matches current registry size
        if len(search_engine.dataset_metadata) == len(dataset_registry):
            if search_engine.config.show_progress:
                print("✅ Using existing embeddings", file=sys.stderr, flush=True)
            return search_engine
        else:
            if search_engine.config.show_progress:
                print("⚠️ Registry size mismatch, rebuilding embeddings...", file=sys.stderr, flush=True)

    # Build new embeddings
    search_engine.build_embeddings(dataset_registry)
    return search_engine
