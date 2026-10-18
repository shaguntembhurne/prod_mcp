#!/usr/bin/env python3
"""
Utility script to precompute embeddings for the dataset registry.
"""

import sys
from pathlib import Path
import json

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from semantic_search import initialize_semantic_search
except ImportError as e:
    print(f"Error importing semantic search: {e}")
    print("Install required packages with: uv sync")
    sys.exit(1)


def load_dataset_registry():
    """Load the dataset registry from the JSON file."""
    registry_path = Path(__file__).parent / "data" / "data_gov_in_api_registry.json"
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Registry file not found at {registry_path}")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ Invalid JSON in registry file: {e}")
        return []


def main():
    """Main function to build embeddings."""
    print("🚀 Starting embedding precomputation...")

    # First ensure model is downloaded
    print("📥 Checking if model is downloaded locally...")
    models_dir = Path(__file__).parent / "models"

    # Get model name from config
    from config_loader import get_config

    config = get_config()
    model_name = config.get("semantic_search", "model_name")

    # Check if model exists locally
    model_exists = False
    if models_dir.exists():
        model_files = list(models_dir.rglob(f"*{model_name}*"))
        model_exists = len(model_files) > 0

    if not model_exists:
        print(f"📦 Model {model_name} not found locally, downloading...")
        try:
            from download_model import download_model

            if not download_model():
                print("❌ Failed to download model")
                sys.exit(1)
        except Exception as e:
            print(f"❌ Error downloading model: {e}")
            sys.exit(1)
    else:
        print(f"✅ Model {model_name} found locally")

    # Load dataset registry
    dataset_registry = load_dataset_registry()
    if not dataset_registry:
        print("❌ No datasets found in registry")
        sys.exit(1)

    print(f"📊 Found {len(dataset_registry)} datasets in registry")

    # Initialize semantic search and build embeddings
    try:
        search_engine = initialize_semantic_search(dataset_registry, force_rebuild=True)
        print("✅ Embeddings built successfully!")

        # Test search
        test_results = search_engine.search("health HIV", limit=3)
        print(f"\n🧪 Test search for 'health HIV' found {len(test_results)} results:")
        for i, result in enumerate(test_results, 1):
            print(f"  {i}. {result['title']} (score: {result['similarity_score']:.3f})")

    except Exception as e:
        print(f"❌ Error building embeddings: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
