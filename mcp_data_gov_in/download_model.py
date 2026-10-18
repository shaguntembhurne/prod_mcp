#!/usr/bin/env python3
"""
Download and cache the sentence transformer model locally.
"""

import os
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config_loader import get_config


def download_model():
    """Download the sentence transformer model to local models directory."""
    try:
        from sentence_transformers import SentenceTransformer

        # Get model name from config
        config = get_config()
        model_name = config.get("semantic_search", "model_name")

        # Set up local model directory
        models_dir = Path(__file__).parent / "models"
        models_dir.mkdir(exist_ok=True)

        print("🔄 Downloading sentence transformer model to local directory...")
        print(f"📁 Model cache directory: {models_dir}")
        print(f"🤖 Model: {model_name}")

        # Set environment variables to use local cache
        os.environ["TRANSFORMERS_CACHE"] = str(models_dir)
        os.environ["SENTENCE_TRANSFORMERS_HOME"] = str(models_dir)

        # Download the model
        model = SentenceTransformer(model_name, cache_folder=str(models_dir))

        print("✅ Model downloaded successfully!")

        # Test the model
        print("🧪 Testing model...")
        test_text = "This is a test sentence."
        embedding = model.encode([test_text])
        print(f"✅ Model test passed! Embedding shape: {embedding.shape}")

        # Show model files
        model_files = list(models_dir.rglob("*"))
        print(f"📊 Downloaded {len(model_files)} model files")

        return True

    except ImportError:
        print("Error: sentence-transformers not installed.")
        print("Install required packages with: uv sync")
        return False
    except Exception as e:
        print(f"❌ Error downloading model: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Main function."""
    print("🚀 Downloading sentence transformer model locally...\n")

    if download_model():
        print("\n🎉 Model download completed successfully!")
        print("The project is now self-contained with the model stored locally.")
        return 0
    else:
        print("\n❌ Model download failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
