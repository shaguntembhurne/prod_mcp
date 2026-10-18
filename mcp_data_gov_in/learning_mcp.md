# Learning MCP Server Development

This document uses the `mcp_data_gov_in` project as a case study to explain how to build Model Context Protocol (MCP) servers using FastMCP v2.

## 📚 Table of Contents

1. [MCP Fundamentals](#mcp-fundamentals)
2. [Project Setup and Structure](#project-setup-and-structure)
3. [Core MCP Components](#core-mcp-components)
4. [Tools Implementation](#tools-implementation)
5. [Resources Implementation](#resources-implementation)
6. [Configuration and Environment](#configuration-and-environment)
7. [Error Handling Patterns](#error-handling-patterns)
8. [Advanced Features](#advanced-features)
9. [Best Practices](#best-practices)

## 🔍 MCP Fundamentals

### What is MCP?

The Model Context Protocol (MCP) is an open standard for connecting AI assistants with external tools and data sources. It defines a client-server architecture where:
- **MCP Client**: AI assistants like Claude Desktop
- **MCP Server**: Your application that provides tools and resources

### Key Concepts

1. **Tools**: Functions that the AI can call to perform actions
2. **Resources**: Static or dynamic data that the AI can read
3. **Prompts**: Pre-defined conversation starters (not used in this project)

## 🏗️ Project Setup and Structure

### Dependencies

Looking at our `pyproject.toml`, an MCP server with semantic search needs:

```toml
[project]
name = "mcp-data-gov-in"
version = "2.0.0"
description = "MCP server for data.gov.in, implementing semantic search for dataset discovery and enabling analysis."
requires-python = ">=3.12"
dependencies = [
    "faiss-cpu>=1.8.0",
    "fastmcp>=2.10.0",
    "httpx>=0.28.1",
    "numpy>=1.24.0",
    "pandas>=2.0.0",
    "pytest>=8.2.1",
    "pytest-asyncio>=0.23.6",
    "sentence-transformers>=2.7.0",
]
```

**Key Dependencies Explained:**
- `mcp`: Official Model Context Protocol SDK
- `httpx`: Async HTTP client for API calls
- `sentence-transformers`: Provides pre-trained embedding models
- `faiss-cpu`: Facebook's library for efficient similarity search
- `numpy`: Required for vector operations

### Project Architecture

Our project follows a modular architecture with semantic search capabilities:

```
mcp_server.py           # Main MCP server implementation
├── Configuration       # Environment and data loading
├── Semantic Search     # AI-powered dataset discovery
├── Utility Functions   # Helper functions for data processing
├── Server Init         # FastMCP instance and setup
├── MCP Resources       # Data sources for the AI
├── MCP Tools          # Functions the AI can execute
└── Main Entry Point    # Server startup logic

semantic_search.py      # Semantic search implementation
├── DatasetSemanticSearch  # Main search class
├── Embedding Model     # sentence-transformers integration
├── FAISS Index        # Vector similarity search
└── Local Caching      # Model and embeddings storage

Supporting Scripts:
├── download_model.py   # Download and cache embedding model
├── build_embeddings.py # Precompute dataset embeddings
└── embeddings/        # Cached model and embeddings directory
```

## 🛠️ Core MCP Components

### 1. Server Initialization

The foundation of any MCP server is the FastMCP instance:

```python
from fastmcp import FastMCP

# Create the FastMCP server instance
mcp = FastMCP("data-gov-in-mcp")
```

**Key Learning Points:**
- Use a descriptive server name
- FastMCP handles all MCP protocol details
- The server name appears in Claude Desktop's MCP server list

### 2. Server Lifecycle

The main function demonstrates the standard MCP server lifecycle:

```python
def main() -> None:
    """Run the MCP server."""
    print("Starting simple MCP server...", file=sys.stderr)
    
    # Configuration checks
    if not API_KEY:
        print("⚠ WARNING: DATA_GOV_API_KEY environment variable not set", file=sys.stderr)
    
    # Start the server
    mcp.run(transport="stdio")
```

**Key Learning Points:**
- Use `mcp.run(transport="stdio")` for Claude Desktop integration
- Print status messages to `sys.stderr` (not stdout)
- Perform configuration validation before starting

### 🚀 Migration to FastMCP v2

This project was recently migrated from the official MCP SDK to FastMCP v2, which provides several advantages:

#### **Why FastMCP v2?**
- **Enhanced Performance**: Improved protocol handling and reduced boilerplate
- **Better Developer Experience**: More Pythonic interface with cleaner decorators
- **Advanced Features**: Built-in support for authentication, proxy servers, and composition
- **Active Development**: FastMCP v2 is actively maintained with frequent updates
- **Production Ready**: Comprehensive testing frameworks and deployment tools

#### **Migration Changes**
```python
# Before: Official MCP SDK
from mcp.server import FastMCP

# After: FastMCP v2
from fastmcp import FastMCP

# Server lifecycle change
# Before: async function with await
async def main():
    await mcp.run_stdio_async()

# After: synchronous function
def main():
    mcp.run(transport="stdio")
```

#### **Dependency Updates**
- **Removed**: `mcp>=1.10.0`
- **Added**: `fastmcp>=2.10.0` via pip
- **Updated**: `httpx>=0.28.1` (required by FastMCP v2)

#### **Backward Compatibility**
- All existing tools and resources work unchanged
- Same decorator patterns (`@mcp.tool()`, `@mcp.resource()`)
- Same client integration (Claude Desktop configuration unchanged)

## 🧠 Multi-Query Semantic Search Architecture

This project implements AI-powered semantic search optimized for **multi-query discovery** that finds both specific and filterable general datasets simultaneously.

### Multi-Query Search Philosophy

The search system is designed to:
- **Multiple Simultaneous Queries**: Execute 2-5 related queries at once for comprehensive coverage
- **General + Specific Discovery**: Find both filterable general datasets and targeted specific datasets  
- **Strategic Result Organization**: Top results per query organized for clear analysis
- **Cross-Query Relevance**: Identify datasets appearing across multiple queries as highly relevant

### Components

1. **Embedding Model**: `all-MiniLM-L6-v2` from sentence-transformers
2. **Vector Database**: FAISS for fast similarity search across multiple queries
3. **Precomputed Embeddings**: Built once, reused for all searches
4. **Local Caching**: Model downloaded and cached locally
5. **Multi-Query Coordination**: Execute multiple searches and organize results strategically
6. **Relevance Filtering**: Automatic filtering of low-similarity results

### Implementation Structure

```
semantic_search.py       # Core semantic search engine
download_model.py        # Download and cache the embedding model  
build_embeddings.py      # Precompute dataset embeddings
models/                 # Directory for cached model
data/                   # Directory for cached embeddings and index
```

### Key Features

- **Multi-Query Processing**: Handle multiple related queries simultaneously
- **Smart Result Organization**: Results organized by query for strategic analysis
- **General vs Specific Detection**: Identify filterable general datasets vs targeted specific ones
- **Cross-Query Relevance**: Highlight datasets appearing in multiple queries
- **Title Prioritization**: Dataset titles weighted higher than descriptions
- **Automatic Quality Filtering**: Low-relevance results filtered out based on configurable thresholds
- **Local Operation**: No external API calls required for search

### Multi-Query Strategy Implementation

The search tools implement a "multiple-angles-simultaneously" philosophy:

```python
# Multi-query approach for comprehensive discovery
queries = ['flight data', 'airline flights', 'Air India flights', 'Delhi airport data']
# Returns: General filterable datasets + specific targeted datasets

# Strategic result organization
results_by_query = {
    'flight data': [general_datasets_filterable_for_airlines_and_airports],
    'airline flights': [airline_specific_datasets],  
    'Air India flights': [air_india_specific_datasets],
    'Delhi airport data': [delhi_airport_specific_datasets]
}

# Cross-query analysis for high-relevance identification
high_relevance_datasets = find_datasets_across_multiple_queries(results_by_query)
```

### Real-World Use Case Optimization

The system is optimized for practical questions like:
- "Air India flights landing in Delhi" → ['flight data', 'airline flights', 'Air India flights', 'Delhi airport data']
- "Maharashtra wheat production trends" → ['agriculture data', 'crop production', 'wheat production', 'Maharashtra agriculture']
- "Government hospital capacity in Karnataka" → ['health data', 'hospital data', 'government hospitals', 'Karnataka health']

This finds both general datasets (that can be filtered) and specific datasets (that provide targeted data) for comprehensive analysis.
- **Fast Performance**: Precomputed embeddings enable instant search

### Initialization Pattern

```python
# Import semantic search functionality
try:
    from semantic_search import initialize_semantic_search, DatasetSemanticSearch
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Semantic search not available: {e}", file=sys.stderr)
    SEMANTIC_SEARCH_AVAILABLE = False

# Initialize semantic search if available
SEMANTIC_SEARCH_ENGINE = None
if SEMANTIC_SEARCH_AVAILABLE and DATASET_REGISTRY:
    try:
        print("🔄 Initializing semantic search...", file=sys.stderr)
        SEMANTIC_SEARCH_ENGINE = initialize_semantic_search(DATASET_REGISTRY)
        print("✅ Semantic search initialized", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to initialize semantic search: {e}", file=sys.stderr)
```

### Setup Requirements

```bash
# Install semantic search dependencies
uv sync

# Download the embedding model
uv run download_model.py

# Build precomputed embeddings
uv run build_embeddings.py
```

## 🔧 Tools Implementation

### Tool Definition Pattern

**2025 Update: Return Python objects, not JSON strings**

Every MCP tool should return a Python dictionary (or list) for structured data. FastMCP will handle JSON serialization automatically. Only return a string for plain error messages or human-readable output.

```python
@mcp.tool()
async def tool_name(param1: type, param2: type = default) -> dict:
    """Tool description that the AI sees."""
    try:
        # Input validation
        if not some_condition:
            return {"error": "Error message"}
        # Business logic
        result = await some_async_operation()
        return result  # Return as dict, not as JSON string
    except Exception as e:
        return {"error": str(e)}
```

### Example: Semantic Search Tool

```python
@mcp.tool()
async def search_datasets(query: str, limit: int = 5) -> dict:
    """
    Search public datasets on data.gov.in by keyword using AI-powered semantic search.

    This tool uses semantic search to find relevant datasets based on meaning,
    not just keyword matching. The search prioritizes dataset titles over ministry/sector names.
    """
    try:
        # Check if semantic search is available and ready
        if not SEMANTIC_SEARCH_ENGINE:
            return {
                "error": "Semantic search is not initialized. Please ensure the required packages are installed and embeddings are built.",
                "suggestion": "Run 'python build_embeddings.py' to initialize semantic search.",
                "available_packages": SEMANTIC_SEARCH_AVAILABLE
            }
        
        if not SEMANTIC_SEARCH_ENGINE.is_ready():
            return {
                "error": "Semantic search engine is not ready. Embeddings may not be built yet.",
                "suggestion": "Run 'python build_embeddings.py' to build embeddings for semantic search."
            }

        # Use semantic search
        results = SEMANTIC_SEARCH_ENGINE.search(query, limit=limit)

        if not results:
            return {
                "message": f"No datasets found matching '{query}' using semantic search",
                "suggestion": "Try rephrasing your query or using different keywords. For example: health, petroleum, oil, crude, inflation, taxes, or guarantees",
                "total_datasets": len(DATASET_REGISTRY),
                "search_method": "semantic search (AI-powered)"
            }

        # Return results with semantic similarity scores
        return {
            "query": query,
            "found": len(results),
            "total_available": len(DATASET_REGISTRY),
            "search_method": "semantic search (AI-powered)",
            "datasets": results,
            "note": "Results from curated dataset registry using AI-powered semantic search. API key still required for downloading data.",
            "tip": "🔴 MANDATORY: Use inspect_dataset_structure() first on ALL promising datasets, then download_filtered_dataset() to get specific data subsets.",
            "semantic_note": (
                "These results are ranked by semantic similarity. The search prioritizes dataset titles. "
                "Each result includes a similarity_score and full metadata for context."
            )
        }
    except Exception as e:
        return {"error": f"Error in semantic search: {str(e)}"}
```

**Key Learning Points:**
- **Always return Python dictionaries or lists for structured data.**
- FastMCP will serialize your return value to JSON automatically.
- Only return a string for plain error messages or human-readable output.
- Include helpful suggestions in responses.
- Provide guidance on follow-up actions.

### Advanced Tool: Flexible Input Types

The `download_filtered_dataset` tool shows how to handle multiple input types:

```python
@mcp.tool()
async def download_filtered_dataset(
    resource_id: str, 
    column_filters: Union[str, Dict[str, str]], 
    limit: int = 100
) -> str:
    # Parse the column filters - handle both string and dict inputs
    try:
        if isinstance(column_filters, dict):
            filters_dict = column_filters
        elif isinstance(column_filters, str):
            filters_dict = json.loads(column_filters) if column_filters else {}
        else:
            filters_dict = dict(column_filters) if column_filters else {}
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "error": f"Invalid column_filters format. Received: {type(column_filters).__name__}. "
            + 'Expected JSON string like "{\"column_name\": \"filter_value\"}" or a dictionary object.'
        }
```

**Key Learning Points:**
- Use `Union` types for flexible input handling
- Always validate and sanitize inputs
- Provide clear error messages with examples
- Handle edge cases gracefully
- **Return Python objects, not JSON strings, for all structured data.**

## 📊 Resources Implementation

### Resource Definition Pattern

Resources provide static or dynamic data that the AI can read:

```python
@mcp.resource("dataset://registry")
async def get_dataset_registry() -> str:
    """Expose the dataset registry as an MCP resource for metadata browsing."""
    try:
        # Return the full registry with enhanced metadata
        registry_with_metadata = {
            "total_datasets": len(DATASET_REGISTRY),
            "last_updated": "2025-07-08",
            "source": "data.gov.in API registry",
            "datasets": DATASET_REGISTRY,
            "sectors": list({d.get("sector", "Unknown") for d in DATASET_REGISTRY}),
            "ministries": list({d.get("ministry", "Unknown") for d in DATASET_REGISTRY}),
        }

        return json.dumps(registry_with_metadata, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error accessing registry: {str(e)}"
```

**Key Learning Points:**
- Use descriptive URI schemes (`dataset://registry`)
- Resources return strings, just like tools
- Include metadata about the data (counts, last updated, etc.)
- Resources are read-only - use tools for actions

## ⚙️ Configuration and Environment

### Environment Loading

The project shows a clean pattern for configuration:

```python
def load_env_file() -> None:
    """Load environment variables from .env file if it exists."""
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

# Initialize environment and configuration
load_env_file()
API_KEY = os.getenv("DATA_GOV_API_KEY")
```

**Key Learning Points:**
- Use `pathlib.Path` for file operations
- Support both environment variables and `.env` files
- Handle missing configuration gracefully
- Strip whitespace from values

### Data Loading

For performance, load static data once at startup:

```python
def load_dataset_registry() -> List[Dict[str, Any]]:
    """Load the dataset registry from the JSON file."""
    registry_path = Path(__file__).parent / "data" / "data_gov_in_api_registry.json"
    try:
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠ WARNING: Registry file not found at {registry_path}", file=sys.stderr)
        return []
    except json.JSONDecodeError as e:
        print(f"⚠ WARNING: Invalid JSON in registry file: {e}", file=sys.stderr)
        return []

# Load data once at startup
DATASET_REGISTRY = load_dataset_registry()
```

**Key Learning Points:**
- Use proper encoding (`utf-8`) for international data
- Handle file not found and JSON parsing errors
- Return empty collections as fallbacks
- Load data once, use many times

## 🛡️ Error Handling Patterns

### Tool Error Handling

Every tool should handle errors gracefully:

```python
@mcp.tool()
async def some_tool(param: str) -> str:
    try:
        # Input validation
        if not API_KEY:
            return json.dumps({
                "error": "DATA_GOV_API_KEY environment variable not set. Please set it to use this tool."
            }, indent=2)
        
        # Business logic that might fail
        result = await risky_operation(param)
        
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"Error in some_tool: {str(e)}"
```

### HTTP Error Handling

For API calls, handle HTTP errors appropriately:

```python
async def download_api(resource_id: str, api_key: str, limit: int = 100) -> Dict[str, Any]:
    """Download a dataset from data.gov.in API with optional filtering."""
    async with httpx.AsyncClient() as client:
        url = f"https://api.data.gov.in/resource/{resource_id}"
        response = await client.get(url, params=params)
        response.raise_for_status()  # Raises HTTPError for bad responses
        return response.json()
```

**Key Learning Points:**
- Use `raise_for_status()` to catch HTTP errors
- Return consistent error JSON structures
- Include helpful error messages
- Don't expose internal errors to users

## 🚀 Advanced Features

### Intelligent Hybrid Filtering

The project implements an advanced hybrid filtering system that automatically optimizes performance by combining server-side and client-side filtering. This approach provides the best of both worlds: efficiency when possible, completeness always.

#### How Hybrid Filtering Works

```python
def build_server_side_filters(user_filters: Dict[str, str], field_exposed: List[Dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Build server-side and client-side filters from user input.
    
    Analyzes the API's field_exposed metadata to determine which fields
    can be filtered server-side, and automatically builds the appropriate
    filter parameters for both server and client filtering.
    """
    server_filters = {}
    client_filters = {}
    
    for filter_key, filter_value in user_filters.items():
        # Try to find a matching field in field_exposed
        server_field_id = None
        for field in field_exposed:
            field_id = field.get("id", "")
            field_name = field.get("name", "")
            
            # Case-insensitive matching for both id and name
            if (filter_key.lower() == field_id.lower() or 
                filter_key.lower() == field_name.lower()):
                server_field_id = field_id
                break
        
        if server_field_id:
            # Can be filtered server-side using exact API field ID
            server_filters[f"filters[{server_field_id}]"] = filter_value
        else:
            # Fall back to client-side filtering
            client_filters[filter_key] = filter_value
    
    return server_filters, client_filters
```

#### Complete Filtering Implementation

The `download_filtered_dataset` function demonstrates the full hybrid approach:

```python
async def download_filtered_dataset(resource_id: str, column_filters: Union[str, Dict[str, str]], limit: Optional[int] = None) -> dict:
    """
    Download a dataset with intelligent server-side and client-side filtering.
    
    This function automatically:
    1. Analyzes API metadata to determine which filters can be applied server-side
    2. Applies server-side filters during pagination for efficiency
    3. Downloads complete dataset using pagination when needed
    4. Applies remaining filters client-side for completeness
    """
    # Get dataset metadata to determine filterable fields
    metadata = await get_dataset_metadata(resource_id, API_KEY)
    field_exposed = metadata.get("field_exposed", [])
    
    # Build server-side and client-side filters automatically
    server_filters, client_filters = build_server_side_filters(filters_dict, field_exposed)
    
    # Download data with server-side filtering and pagination
    if server_filters or not filters_dict:
        # Use server-side filtering and pagination for efficiency
        result = await download_api_paginated(
            resource_id, API_KEY, server_filters, 
            max_records=config.get("data_api", "max_total_records")
        )
    else:
        # No server-side filters possible, use legacy method
        result = await download_api(resource_id, API_KEY, config.get("data_api", "max_download_limit"))
    
    # Apply client-side filtering if needed
    if client_filters:
        result = filter_dataset_records(result, client_filters)
    
    # Provide comprehensive filtering summary
    result["filtering_summary"] = {
        "total_records_in_dataset": total_available,
        "records_downloaded": total_records,
        "records_after_filtering": filtered_count,
        "server_side_filters": server_filters,
        "client_side_filters": client_filters,
        "filter_criteria": filters_dict,
    }
```

#### Key Learning Points for Hybrid Filtering

**Design Principles:**
- **Transparency**: Users don't need to know which filters are applied where
- **Efficiency**: Server-side filtering reduces data transfer and processing time
- **Completeness**: Client-side fallback ensures no data is missed
- **Robustness**: Graceful degradation when server-side filtering isn't available

**Implementation Strategy:**
- Always analyze API metadata (`field_exposed`) to determine capabilities
- Use exact field IDs from API metadata for server-side filtering
- Apply server-side filters during pagination for maximum efficiency  
- Fall back to client-side filtering for non-server-filterable fields
- Handle field name variations intelligently in client-side filtering (e.g., "Arrival_Date" vs "arrival_date")
- Provide detailed summaries showing where each filter was applied

**Performance Benefits:**
- Dramatically reduced data transfer when server-side filtering is available
- Faster filtering by reducing the amount of data that needs client-side processing
- Transparent to users while providing optimal performance
- Robust field name matching prevents filtering failures due to naming inconsistencies

### Search and Discovery

The search function demonstrates efficient text search, enhanced with intelligent guidance:

```python
def search_static_registry(dataset_registry: List[Dict[str, Any]], query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Search through the dataset registry."""
    query_lower = query.lower()
    results = []

    for dataset in dataset_registry:
        # Search in title, ministry, and sector
        searchable_text = " ".join([
            dataset.get("title", "").lower(),
            dataset.get("ministry", "").lower(),
            dataset.get("sector", "").lower(),
            dataset.get("catalog", "").lower(),
        ])

        # Simple text matching
        if query_lower in searchable_text:
            results.append({
                "resource_id": dataset["resource_id"],
                "title": dataset["title"],
                "ministry": dataset.get("ministry", "Unknown"),
                "sector": dataset.get("sector", "Unknown"),
                "url": dataset.get("url", f"https://www.data.gov.in/resource/{dataset['resource_id']}#api"),
            })

    return results[:limit]
```

### Search Guidance Implementation

The project includes intelligent search guidance to help users find relevant datasets effectively:

```python
@mcp.tool()
async def get_search_guidance(domain: str, current_query: Optional[str] = None) -> dict:
    """Get strategic guidance for effective semantic search based on domain."""
    # Domain-specific strategies with broad and specific terms
    domain_strategies = {
        "health": {
            "broad_terms": ["health", "medical", "healthcare", "disease", "treatment"],
            "specific_terms": ["vaccination", "covid", "hospital", "mortality"],
            "common_filters": {"state": "StateName", "year": "YYYY"},
            "tip": "Health data often spans multiple datasets - search broadly then filter"
        }
        # ... more domains
    }
```

**Search Strategy Patterns:**

1. **Two-Stage Approach**: Broad search → Specific filtering
   - Search: "health" → Filter: `{"state": "Karnataka", "year": "2023"}`
   - Advantages: Finds all relevant datasets, then narrows precisely

2. **Dynamic Guidance**: Context-aware suggestions based on:
   - Query specificity (too broad/narrow)
   - Result quality (relevance scores)
   - Domain characteristics (health vs agriculture patterns)

3. **Progressive Refinement**:
   - No results: Try broader terms → synonyms → domain terms
   - Too many results: Add specific terminology → use filters
   - Good results: Examine all relevant datasets comprehensively

**Key Learning Points:**
- Create searchable text by combining relevant fields
- Use case-insensitive matching
- Return structured, consistent results
- Implement proper result limiting
- Provide intelligent guidance based on search context
- Support both exploratory and targeted search strategies

## 📋 Best Practices

### 1. Code Organization

```python
# ============================================================================
# Configuration and Utility Functions
# ============================================================================
# Helper functions and configuration

# ============================================================================
# Server Initialization
# ============================================================================
# FastMCP setup and global state

# ============================================================================
# MCP Resources
# ============================================================================
# Data sources for the AI

# ============================================================================
# MCP Tools
# ============================================================================
# Functions the AI can execute

# ============================================================================
# Main Entry Point
# ============================================================================
# Server startup logic
```

**Use clear section dividers** to organize your code logically.

### 2. Function Documentation

```python
@mcp.tool()
async def inspect_dataset_structure(resource_id: str, sample_size: int = 5) -> str:
    """
    🔴 MANDATORY: Dataset structure inspection - REQUIRED before any downloads!
    
    You MUST use this function first to understand the data structure before using
    download_dataset() or download_filtered_dataset(). This reveals available columns,
    data types, and filtering possibilities.
    """
```

**Include usage guidance** in docstrings to help the AI use tools effectively.

### 3. Response Structure

```python
structure = {
    "fields": fields,
    "column_names": column_names,
    "sample_records": sample_records,
    "total_records_available": result.get("total", "unknown"),
    "usage_tip": "🔴 INSPECTION COMPLETE: Now use download_filtered_dataset() with column_filters based on the structure you see above",
    "example_filter": f'{{"column_name": "filter_value"}} or as dict {{"column_name": "filter_value"}}' if column_names else "No columns available for filtering"
}
```

**Include usage tips and examples** in responses to guide the AI's next actions.

### 4. Clean API Responses

When designing MCP tool responses, focus on **LLM-useful information** and exclude backend implementation details:

**✅ Include (Useful for LLM):**
```python
structure = {
    "fields": fields,
    "column_names": column_names,
    "field_filtering_guide": field_name_guide,
    "sample_records_csv": sample_csv,
    "total_records_available": result.get("total", "unknown"),
    "usage_tip": "Use download_filtered_dataset() for complete data in CSV format",
    "field_name_tips": {
        "flexible_naming": "You can use either display names or field IDs",
        "case_insensitive": "Field name matching is case-insensitive",
        "date_filtering": "For date fields, use exact format as shown in sample data"
    },
    "example_filter": '{"column_name": "filter_value"}'
}
```

**❌ Exclude (Backend Implementation Details):**
```python
# Don't include these - they confuse LLMs:
"server_filterable": is_server_filterable,
"filter_method": "server-side" if is_server_filterable else "client-side",
"pagination_info": {
    "used_server_filters": bool(server_filters),
    "server_filters_applied": server_filters,
    "automatic_pagination": "Server downloads complete datasets...",
    "no_manual_pagination": "No need to handle pagination manually..."
}
```

**Why Clean Responses Matter:**
- LLMs get confused by technical implementation details
- Focus on what the LLM needs to effectively use the data
- Simpler responses = better tool understanding and usage
- Remove noise that doesn't help with data analysis

### 5. Type Hints

```python
from typing import Dict, Any, List, Optional, Union

def search_static_registry(
    dataset_registry: List[Dict[str, Any]], 
    query: str, 
    limit: int = 10
) -> List[Dict[str, Any]]:
```

**Use comprehensive type hints** for better code maintainability and IDE support.

### 6. Error Messages

```python
return json.dumps({
    "error": f"Invalid column_filters format. Received: {type(column_filters).__name__}. " +
            "Expected JSON string like '{\"column_name\": \"filter_value\"}' or a dictionary object."
}, indent=2)
```

**Provide specific, actionable error messages** with examples.

## 🎯 Semantic Search Best Practices

### 1. Graceful Degradation

```python
# Always check if semantic search is available
if not SEMANTIC_SEARCH_ENGINE:
    return {
        "error": "Semantic search is not initialized.",
        "suggestion": "Run 'python build_embeddings.py' to initialize semantic search.",
        "available_packages": SEMANTIC_SEARCH_AVAILABLE
    }

if not SEMANTIC_SEARCH_ENGINE.is_ready():
    return {
        "error": "Semantic search engine is not ready. Embeddings may not be built yet.",
        "suggestion": "Run 'python build_embeddings.py' to build embeddings for semantic search."
    }
```

### 2. Local Model Caching

```python
# Download model once, cache locally
def download_model():
    """Download and cache the sentence transformer model locally."""
    model_name = "all-MiniLM-L6-v2"
    cache_dir = Path("./embeddings/model_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Downloading model {model_name}...", file=sys.stderr)
    model = SentenceTransformer(model_name, cache_folder=str(cache_dir))
    print(f"✅ Model downloaded and cached at {cache_dir}", file=sys.stderr)
```

### 3. Precomputed Embeddings

```python
# Build embeddings once, reuse for all searches
def build_embeddings(registry_path: str):
    """Build and save embeddings for the dataset registry."""
    with open(registry_path, 'r') as f:
        registry = json.load(f)
    
    # Create combined text for embedding (prioritize titles)
    texts = []
    for dataset in registry:
        title = dataset.get('title', '')
        desc = dataset.get('desc', '')
        # Title gets more weight in the embedding
        combined_text = f"{title} {title} {desc}"
        texts.append(combined_text)
    
    # Compute embeddings
    embeddings = model.encode(texts, show_progress_bar=True)
    
    # Save for fast loading
    np.save(embeddings_path, embeddings)
```

### 4. Similarity Score Interpretation

```python
# Provide guidance when similarity scores are low
if results:
    max_score = max(result.get("similarity_score", 0) for result in results)
    if max_score < 0.3:
        response["relevance_warning"] = (
            "Low similarity scores detected. Please verify if these datasets are relevant "
            "to the user's query before proceeding with data download."
        )
```

### 5. Error Handling for Dependencies

```python
# Handle missing dependencies gracefully
try:
    from semantic_search import initialize_semantic_search, DatasetSemanticSearch
    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Semantic search not available: {e}", file=sys.stderr)
    print("Install required packages with: uv sync", file=sys.stderr)
    SEMANTIC_SEARCH_AVAILABLE = False
```

## 🎯 Common Patterns

### 1. Pure Functions

```python
# Good: Pure function that's easy to test
def filter_dataset_records(data: Dict[str, Any], column_filters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    # No side effects, deterministic output

# Usage in tools
@mcp.tool()
async def download_filtered_dataset(...):
    result = await download_api(resource_id, API_KEY, limit)
    if filters_dict:
        result = filter_dataset_records(result, filters_dict)
```

### 2. Async/Await for I/O

```python
async def download_api(resource_id: str, api_key: str, limit: int = 100) -> Dict[str, Any]:
    """Download a dataset from data.gov.in API with optional filtering."""
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        return response.json()
```

### 3. Resource Management

```python
async with httpx.AsyncClient() as client:
    # Client automatically closed after use
    response = await client.get(url, params=params)
```

## 🔍 Debugging Tips

### 1. Logging to stderr

```python
print("Creating MCP server...", file=sys.stderr)
print(f"✓ Loaded {len(DATASET_REGISTRY)} datasets from registry", file=sys.stderr)
```

### 2. Error Tracking

```python
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
```

### 3. Validation

```python
# Validate configuration
if not API_KEY:
    print("⚠ WARNING: DATA_GOV_API_KEY environment variable not set", file=sys.stderr)
    print("Set DATA_GOV_API_KEY=<your_api_key> for full functionality", file=sys.stderr)
```

## 📖 Further Learning

### Official Documentation
- [MCP Specification](https://spec.modelcontextprotocol.org/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)

### This Project's Key Files
- `mcp_server.py` - Complete MCP server implementation
- `data/data_gov_in_api_registry.json` - Example of curated data
- `environment.yml` - Dependencies and environment setup

This project demonstrates a complete, production-ready MCP server that showcases all the essential patterns and best practices for building robust MCP integrations.

## 🔧 Configuration Management

### Config-First Approach

The project follows a strict config-first approach where all configuration values must be explicitly defined in `config.json`:

- **No Default Values**: The config loader no longer provides default values
- **Explicit Configuration**: All parameters must be present in `config.json`
- **Early Failure**: Missing config keys will cause startup failures, not silent defaults
- **Type Safety**: All config access goes through the centralized config loader

### Configuration Usage

```python
from config_loader import get_config

config = get_config()

# This will raise KeyError if 'model_name' is missing
model_name = config.get("semantic_search", "model_name")

# Use convenience properties where available
threshold = config.relevance_threshold  # Property with direct config access
```

### Benefits

- **Predictable Behavior**: No surprise defaults
- **Easy Debugging**: Missing config is caught early
- **Centralized**: All configuration in one file
- **Maintainable**: No scattered default values throughout codebase
