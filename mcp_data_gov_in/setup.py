#!/usr/bin/env python3
"""
Setup script for MCP Data.gov.in server with semantic search.
"""

import subprocess
import sys
from pathlib import Path


def run_command(command, description):
    """Run a command and print the result."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ {description} completed")
            return True
        else:
            print(f"❌ {description} failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ {description} failed: {e}")
        return False


def check_packages():
    """Check if required packages are installed."""
    required_packages = ["sentence_transformers", "faiss", "numpy", "httpx", "fastmcp"]

    missing_packages = []
    for package in required_packages:
        try:
            __import__(package.replace("-", "_"))
        except ImportError:
            missing_packages.append(package)

    return missing_packages


def main():
    """Main setup function."""
    print("🚀 Setting up MCP Data.gov.in server with semantic search...\n")

    # Check current directory
    current_dir = Path.cwd()
    expected_files = ["mcp_server.py", "semantic_search.py", "data/data_gov_in_api_registry.json"]

    missing_files = []
    for file in expected_files:
        if not (current_dir / file).exists():
            missing_files.append(file)

    if missing_files:
        print(f"❌ Missing required files: {', '.join(missing_files)}")
        print("Please run this script from the project root directory.")
        return 1

    print("✅ Project structure verified")

    # Check packages
    missing_packages = check_packages()
    if missing_packages:
        print(f"📦 Missing packages detected: {', '.join(missing_packages)}")

        # Try to install using uv
        if not run_command("uv sync", "Installing packages with uv"):
            print("❌ Package installation failed")
            print("Try manually installing: uv sync")
            return 1
    else:
        print("✅ All required packages are installed")

    # Download model locally
    print("\n📥 Downloading sentence transformer model locally...")
    if not run_command("uv run download_model.py", "Downloading model"):
        print("❌ Model download failed")
        return 1

    # Build embeddings
    print("\n🔄 Building embeddings (this may take a few minutes)...")
    if not run_command("uv run build_embeddings.py", "Building embeddings"):
        print("❌ Embedding build failed")
        return 1

    # Test semantic search
    print("\n🧪 Testing semantic search...")
    if not run_command(
        "uv run pytest tests/test_tools.py::test_semantic_search_functionality -v", "Testing semantic search"
    ):
        print("⚠️ Semantic search test failed, but server should still work with fallback")

    print("\n🎉 Setup completed successfully!")
    print("\nNext steps:")
    print("1. Set your DATA_GOV_API_KEY environment variable")
    print("2. Configure Claude Desktop with the server path")
    print("3. Restart Claude Desktop")
    print("4. Test with: 'Search for health datasets in India'")

    return 0


if __name__ == "__main__":
    sys.exit(main())
