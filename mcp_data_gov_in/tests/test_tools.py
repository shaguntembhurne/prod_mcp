import pytest
import tempfile
import shutil
from pathlib import Path
import sys

# Add the parent directory to path so we can import mcp_server
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server import filter_dataset_records, load_dataset_registry, DATASET_REGISTRY, build_server_side_filters

# Try to import semantic search, but don't fail if packages aren't installed
try:
    from semantic_search import DatasetSemanticSearch, SemanticSearchConfig

    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError:
    SEMANTIC_SEARCH_AVAILABLE = False


# Note: search_static_registry has been replaced by semantic search
# These tests have been removed as the functionality is now part of semantic search


def test_filter_dataset_records():
    """Test the dataset record filtering functionality."""
    # Test data
    test_data = {
        "records": [
            {"state": "Maharashtra", "year": "2023", "value": 100},
            {"state": "Gujarat", "year": "2023", "value": 200},
            {"state": "Maharashtra", "year": "2022", "value": 150},
            {"state": "Karnataka", "year": "2023", "value": 180},
        ],
        "total": 4,
        "field": [{"id": "state"}, {"id": "year"}, {"id": "value"}],
    }

    # Test filtering by state
    filtered = filter_dataset_records(test_data, {"state": "Maharashtra"})
    assert len(filtered["records"]) == 2
    assert filtered["total"] == 2
    assert all(record["state"] == "Maharashtra" for record in filtered["records"])

    # Test filtering by multiple criteria
    filtered = filter_dataset_records(test_data, {"state": "Maharashtra", "year": "2023"})
    assert len(filtered["records"]) == 1
    assert filtered["total"] == 1
    assert filtered["records"][0]["state"] == "Maharashtra"
    assert filtered["records"][0]["year"] == "2023"

    # Test no filters
    filtered = filter_dataset_records(test_data, {})
    assert len(filtered["records"]) == 4
    assert filtered["total"] == 4

    # Test empty data
    empty_data = {"records": [], "total": 0}
    filtered = filter_dataset_records(empty_data, {"state": "Maharashtra"})
    assert len(filtered["records"]) == 0
    assert filtered["total"] == 0


def test_load_dataset_registry():
    """Test that the dataset registry loads correctly."""
    registry = load_dataset_registry()
    assert isinstance(registry, list)
    # Should have some datasets (assuming the file exists)
    if registry:
        assert isinstance(registry[0], dict)
        assert "resource_id" in registry[0]
        assert "title" in registry[0]


@pytest.mark.asyncio
async def test_registry_is_loaded():
    """Test that the global registry is loaded at startup."""
    assert isinstance(DATASET_REGISTRY, list)
    # The registry should be loaded from the JSON file
    # This tests that the startup process works correctly


def test_search_registry_case_insensitive():
    """Test case sensitivity - replaced by semantic search tests."""
    # This functionality is now handled by semantic search
    # See semantic search tests below
    pass


def test_filter_records_case_insensitive():
    """Test that filtering is case insensitive."""
    test_data = {
        "records": [
            {"state": "Maharashtra", "year": "2023"},
            {"state": "GUJARAT", "year": "2023"},
            {"state": "karnataka", "year": "2023"},
        ],
        "total": 3,
    }

    # Test case insensitive filtering
    filtered = filter_dataset_records(test_data, {"state": "maharashtra"})
    assert len(filtered["records"]) == 1
    assert filtered["records"][0]["state"] == "Maharashtra"

    filtered = filter_dataset_records(test_data, {"state": "gujarat"})
    assert len(filtered["records"]) == 1
    assert filtered["records"][0]["state"] == "GUJARAT"


def test_filter_records_field_name_mapping():
    """Test that filtering handles field name variations correctly."""
    test_data = {
        "records": [
            {"arrival_date": "16/07/2025", "commodity": "Tomato", "state": "Maharashtra"},
            {"arrival_date": "15/07/2025", "commodity": "Onion", "state": "Gujarat"},
            {"arrival_date": "16/07/2025", "commodity": "Potato", "state": "Karnataka"},
        ],
        "total": 3,
    }

    # Test filtering using display name style "Arrival_Date" when actual field is "arrival_date"
    filtered = filter_dataset_records(test_data, {"Arrival_Date": "16/07/2025"})
    assert len(filtered["records"]) == 2
    assert filtered["total"] == 2
    assert all(record["arrival_date"] == "16/07/2025" for record in filtered["records"])

    # Test case-insensitive field name matching
    filtered = filter_dataset_records(test_data, {"ARRIVAL_DATE": "16/07/2025"})
    assert len(filtered["records"]) == 2
    assert filtered["total"] == 2

    # Test exact field name still works
    filtered = filter_dataset_records(test_data, {"arrival_date": "16/07/2025"})
    assert len(filtered["records"]) == 2
    assert filtered["total"] == 2

    # Test combined filtering with field name variations
    filtered = filter_dataset_records(test_data, {"Arrival_Date": "16/07/2025", "commodity": "Tomato"})
    assert len(filtered["records"]) == 1
    assert filtered["records"][0]["commodity"] == "Tomato"
    assert filtered["records"][0]["arrival_date"] == "16/07/2025"


@pytest.fixture
def temp_semantic_search():
    """Create a temporary semantic search instance with temporary file paths."""
    if not SEMANTIC_SEARCH_AVAILABLE:
        pytest.skip("Semantic search packages not installed")

    # Create a temporary directory for test embeddings
    temp_dir = tempfile.mkdtemp()
    temp_path = Path(temp_dir)

    try:
        # Create a custom config that uses temporary file paths
        config = SemanticSearchConfig(cache_embeddings=True, show_progress=False)  # Disable progress for tests

        search_engine = DatasetSemanticSearch(config=config)

        # Override the file paths to use temporary directory
        search_engine.embeddings_path = temp_path / "test_embeddings.pkl"
        search_engine.index_path = temp_path / "test_faiss_index.bin"
        search_engine.metadata_path = temp_path / "test_metadata.pkl"

        yield search_engine

    finally:
        # Clean up temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.skipif(not SEMANTIC_SEARCH_AVAILABLE, reason="Semantic search packages not installed")
def test_semantic_search_initialization(temp_semantic_search):
    """Test semantic search initialization with temporary files."""
    if not DATASET_REGISTRY:
        pytest.skip("No dataset registry loaded")

    # Test with a small subset for faster testing
    sample_registry = DATASET_REGISTRY[:10] if len(DATASET_REGISTRY) > 10 else DATASET_REGISTRY

    search_engine = temp_semantic_search
    search_engine.preload_model()
    search_engine.build_embeddings(sample_registry)

    assert search_engine.is_ready()
    assert len(search_engine.dataset_metadata) == len(sample_registry)

    # Verify that temporary files are created
    assert search_engine.embeddings_path.exists()
    assert search_engine.index_path.exists()
    assert search_engine.metadata_path.exists()


@pytest.mark.skipif(not SEMANTIC_SEARCH_AVAILABLE, reason="Semantic search packages not installed")
def test_semantic_search_functionality(temp_semantic_search):
    """Test semantic search functionality with temporary files."""
    if not DATASET_REGISTRY:
        pytest.skip("No dataset registry loaded")

    # Test with a small subset for faster testing
    sample_registry = DATASET_REGISTRY[:10] if len(DATASET_REGISTRY) > 10 else DATASET_REGISTRY

    search_engine = temp_semantic_search
    search_engine.preload_model()
    search_engine.build_embeddings(sample_registry)

    # Test search
    results = search_engine.search("health", limit=3)
    assert isinstance(results, list)
    assert len(results) <= 3

    # Check result structure
    if results:
        result = results[0]
        assert "resource_id" in result
        assert "title" in result
        assert "similarity_score" in result
        assert "metadata" in result
        assert isinstance(result["similarity_score"], (int, float))


def test_searchable_text_creation():
    """Test the creation of searchable text for semantic search."""
    if not SEMANTIC_SEARCH_AVAILABLE:
        pytest.skip("Semantic search packages not installed")

    # Create a temporary search engine just for testing text creation
    config = SemanticSearchConfig(show_progress=False)
    search_engine = DatasetSemanticSearch(config=config)

    test_dataset = {
        "title": "Health Data Survey",
        "ministry": "Ministry of Health",
        "sector": "Health",
        "resource_id": "test-123",
    }

    searchable_text = search_engine._create_searchable_text(test_dataset)

    # Title should appear 3 times for higher weight
    assert searchable_text.count("Health Data Survey") == 3
    assert "Ministry of Health" in searchable_text
    assert "Health" in searchable_text


def test_build_server_side_filters():
    """Test the server-side filter building functionality."""

    # Mock field_exposed data based on real API structure
    field_exposed = [
        {"id": "state.keyword", "name": "State", "type": "string"},
        {"id": "year", "name": "Year", "type": "integer"},
        {"id": "district.keyword", "name": "District", "type": "string"},
        {"id": "scheme_name", "name": "Scheme Name", "type": "string"},
        {"id": "amount", "name": "Amount", "type": "float"},
    ]

    # Test basic field mapping
    user_filters = {"state": "Maharashtra", "year": "2023"}
    server_filters, client_filters = build_server_side_filters(user_filters, field_exposed)

    # Should map 'state' to 'state.keyword' for server-side filtering
    assert "filters[state.keyword]" in server_filters
    assert server_filters["filters[state.keyword]"] == "Maharashtra"

    # Should map 'year' to 'year' for server-side filtering
    assert "filters[year]" in server_filters
    assert server_filters["filters[year]"] == "2023"

    # No client-side filters needed since all fields are mappable
    assert len(client_filters) == 0

    # Test unmappable fields fall back to client-side
    user_filters = {"state": "Maharashtra", "unmappable_field": "value"}
    server_filters, client_filters = build_server_side_filters(user_filters, field_exposed)

    assert "filters[state.keyword]" in server_filters
    assert server_filters["filters[state.keyword]"] == "Maharashtra"
    assert "unmappable_field" in client_filters
    assert client_filters["unmappable_field"] == "value"

    # Test case-insensitive field matching
    user_filters = {"State": "Maharashtra", "DISTRICT": "Mumbai"}
    server_filters, client_filters = build_server_side_filters(user_filters, field_exposed)

    # Should map both regardless of case
    assert "filters[state.keyword]" in server_filters
    assert "filters[district.keyword]" in server_filters
    assert len(client_filters) == 0

    # Test empty inputs
    server_filters, client_filters = build_server_side_filters({}, field_exposed)
    assert len(server_filters) == 0
    assert len(client_filters) == 0

    server_filters, client_filters = build_server_side_filters(user_filters, [])
    assert len(server_filters) == 0
    assert len(client_filters) == len(user_filters)

    # Test field name mapping (using 'name' from field_exposed)
    user_filters = {"State": "Maharashtra", "Year": "2023"}
    server_filters, client_filters = build_server_side_filters(user_filters, field_exposed)

    # Should still map correctly using field names
    assert "filters[state.keyword]" in server_filters or "filters[year]" in server_filters


def test_build_server_side_filters_edge_cases():
    """Test edge cases for server-side filter building."""

    # Field with no 'id' should be skipped
    field_exposed = [
        {"name": "State", "type": "string"},  # No 'id' field
        {"id": "year", "name": "Year", "type": "integer"},
    ]

    user_filters = {"state": "Maharashtra", "year": "2023"}
    server_filters, client_filters = build_server_side_filters(user_filters, field_exposed)

    # Only 'year' should be server-side filterable
    assert "filters[year]" in server_filters
    assert "state" in client_filters

    # Test with duplicate field mappings
    field_exposed = [
        {"id": "state", "name": "State", "type": "string"},
        {"id": "state.keyword", "name": "State Keyword", "type": "string"},
    ]

    user_filters = {"state": "Maharashtra"}
    server_filters, client_filters = build_server_side_filters(user_filters, field_exposed)

    # Should pick one of the mappings (the first one found)
    assert len([k for k in server_filters.keys() if "state" in k]) >= 1
