#!/usr/bin/env python3
"""
Simple standalone MCP server for data.gov.in using FastMCP with semantic search.
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Union, Annotated

import httpx
import pandas as pd
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError, ValidationError, ResourceError
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from pydantic import Field, field_validator

from config_loader import get_config
from rate_limiter import SimpleRateLimiter
from security_utils import validate_query_list, validate_resource_id, validate_filters, log_security_event

# Import semantic search functionality
try:
    from semantic_search import initialize_semantic_search, DatasetSemanticSearch

    SEMANTIC_SEARCH_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Semantic search not available: {e}", file=sys.stderr)
    print(
        "Install required packages with: uv sync",
        file=sys.stderr,
    )
    SEMANTIC_SEARCH_AVAILABLE = False


# ============================================================================
# Configuration and Utility Functions
# ============================================================================

# data.gov.in blocks/hangs requests using httpx's default User-Agent header,
# so we spoof a standard browser-like one for all outbound requests.
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; mcp-data-gov-in/1.0)"}


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


async def get_dataset_metadata(resource_id: str, api_key: str) -> Dict[str, Any]:
    """Get dataset metadata including field information for filtering."""
    params = {
        "api-key": api_key,
        "format": "json",
        "limit": 0,  # Get metadata only
    }

    config = get_config()
    timeout = config.get("data_api", "request_timeout", 30)

    try:
        async with httpx.AsyncClient(timeout=timeout, headers=HTTP_HEADERS) as client:
            url = f"https://api.data.gov.in/resource/{resource_id}"
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise ToolError(f"Request timeout while fetching metadata for resource {resource_id}")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise ToolError(f"Dataset {resource_id} not found")
        elif e.response.status_code == 403:
            raise ToolError("API key invalid or access denied")
        else:
            raise ToolError(f"HTTP error {e.response.status_code} while fetching metadata")
    except Exception as e:
        raise ToolError(f"Unexpected error fetching metadata: {str(e)}")


def build_server_side_filters(
    column_filters: Dict[str, str], field_exposed: List[Dict[str, Any]]
) -> tuple[Dict[str, str], Dict[str, str]]:
    """
    Build server-side filters and return remaining client-side filters.

    Returns:
        tuple: (server_side_filters, client_side_filters)
    """
    if not column_filters:
        return {}, {}

    # Create mapping of field names to their filter-capable versions
    # Only fields in field_exposed can be filtered server-side
    filterable_fields = {}
    for field in field_exposed:
        field_id = field.get("id", "")
        field_name = field.get("name", "")
        if field_id:
            # Use the exact field ID from field_exposed for filtering
            base_name = field_id.replace(".keyword", "")
            filterable_fields[base_name] = field_id
            if field_name and field_name.lower() != base_name:
                filterable_fields[field_name.lower()] = field_id

    server_side_filters = {}
    client_side_filters = {}

    for column, value in column_filters.items():
        column_lower = column.lower()

        # Check if this field can be filtered server-side using field_exposed
        if column in filterable_fields:
            filter_key = f"filters[{filterable_fields[column]}]"
            server_side_filters[filter_key] = value
        elif column_lower in filterable_fields:
            filter_key = f"filters[{filterable_fields[column_lower]}]"
            server_side_filters[filter_key] = value
        else:
            # Fall back to client-side filtering
            client_side_filters[column] = value

    return server_side_filters, client_side_filters


def convert_data_to_csv(data: Dict[str, Any]) -> str:
    """
    Convert dataset records to CSV format using pandas.

    Args:
        data: Dictionary containing 'records' key with list of data records

    Returns:
        str: CSV formatted string
    """
    records = data.get("records", [])
    if not records:
        return "No data available"

    # Convert to pandas DataFrame
    df = pd.DataFrame(records)

    # Convert to CSV string
    return df.to_csv(index=False)


async def download_api_paginated(
    resource_id: str, api_key: str, server_filters: Optional[Dict[str, str]] = None, max_records: Optional[int] = None
) -> Dict[str, Any]:
    """
    Download complete dataset with pagination and server-side filtering.

    Args:
        resource_id: Dataset resource ID
        api_key: API key for data.gov.in
        server_filters: Server-side filters in data.gov.in format
        max_records: Maximum total records to download (None for unlimited)
    """
    config = get_config()
    pagination_limit = config.get("data_api", "pagination_limit")
    max_total_records = max_records or config.get("data_api", "max_total_records")

    all_records = []
    offset = 0
    total_available = None
    metadata = None

    while True:
        params = {
            "api-key": api_key,
            "format": "json",
            "limit": pagination_limit,
            "offset": offset,
        }

        # Add server-side filters
        if server_filters:
            params.update(server_filters)

        async with httpx.AsyncClient(timeout=config.get("data_api", "request_timeout"), headers=HTTP_HEADERS) as client:
            url = f"https://api.data.gov.in/resource/{resource_id}"
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        # Store metadata from first response
        if metadata is None:
            metadata = {
                key: value for key, value in data.items() if key not in ["records", "total", "count", "limit", "offset"]
            }
            total_available = data.get("total", 0)

        records = data.get("records", [])
        if not records:
            break

        all_records.extend(records)

        # Check if we've reached our limits
        if len(all_records) >= max_total_records:
            all_records = all_records[:max_total_records]
            break

        # Check if we've downloaded everything available
        if len(records) < pagination_limit:
            break

        offset += pagination_limit

    # Construct final response
    result = metadata.copy() if metadata else {}
    result.update(
        {
            "records": all_records,
            "total": total_available or len(all_records),
            "count": len(all_records),
        }
    )

    return result


async def download_api(
    resource_id: str, api_key: str, limit: int = 100, filters: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Download a dataset from data.gov.in API with optional filtering (legacy interface)."""
    # Convert to new format for backwards compatibility
    server_filters = {}
    if filters:
        # Simple conversion - assume all filters are server-side for legacy calls
        for key, value in filters.items():
            if not key.startswith("filters["):
                server_filters[f"filters[{key}]"] = value
            else:
                server_filters[key] = value

    # Use new paginated function but limit to single page for compatibility
    config = get_config()
    params = {
        "api-key": api_key,
        "format": "json",
        "limit": min(limit, config.get("data_api", "max_download_limit")),
    }

    if server_filters:
        params.update(server_filters)

    async with httpx.AsyncClient(timeout=config.get("data_api", "request_timeout"), headers=HTTP_HEADERS) as client:
        url = f"https://api.data.gov.in/resource/{resource_id}"
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()


def filter_dataset_records(data: Dict[str, Any], column_filters: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Filter dataset records based on column values with intelligent field name mapping.

    Handles field name variations (e.g., "Arrival_Date" vs "arrival_date") and provides
    better matching for dates and other field types.
    """
    if not column_filters or not data.get("records"):
        return data

    # Build field name mapping from the dataset
    records = data.get("records", [])
    if not records:
        return data

    # Create mapping of user filter names to actual record field names
    sample_record = records[0]
    field_mapping = {}

    for filter_field_name in column_filters.keys():
        # Try exact match first
        if filter_field_name in sample_record:
            field_mapping[filter_field_name] = filter_field_name
        else:
            # Try case-insensitive matching
            filter_field_lower = filter_field_name.lower()
            for record_field in sample_record.keys():
                if record_field.lower() == filter_field_lower:
                    field_mapping[filter_field_name] = record_field
                    break

            # If still no match, try name variations (underscores, etc.)
            if filter_field_name not in field_mapping:
                # Convert variations like "Arrival_Date" to "arrival_date"
                normalized_filter = filter_field_name.lower().replace(" ", "_")
                for record_field in sample_record.keys():
                    normalized_record = record_field.lower().replace(" ", "_")
                    if normalized_filter == normalized_record:
                        field_mapping[filter_field_name] = record_field
                        break

    filtered_records = []
    for record in records:
        match = True
        for filter_field_name, filter_value in column_filters.items():
            # Get the actual field name in the record
            actual_field_name = field_mapping.get(filter_field_name)

            if actual_field_name is None:
                # Field not found in record, no match
                match = False
                break

            record_value = str(record.get(actual_field_name, ""))
            filter_value_str = str(filter_value)

            # For exact date matching, try both exact and substring matching
            if "/" in filter_value_str and "/" in record_value:
                # Date field - try exact match first, then substring
                if record_value.strip() == filter_value_str.strip():
                    continue  # Exact match found
                elif filter_value_str.lower() in record_value.lower():
                    continue  # Substring match found
                else:
                    match = False
                    break
            else:
                # Regular field - case-insensitive substring matching
                if filter_value_str.lower() in record_value.lower():
                    continue  # Match found
                else:
                    match = False
                    break

        if match:
            filtered_records.append(record)

    # Return filtered data with original structure
    filtered_data = data.copy()
    filtered_data["records"] = filtered_records
    filtered_data["total"] = len(filtered_records)

    # Add debug info about field mapping
    if column_filters:
        filtered_data["field_mapping_used"] = field_mapping

    return filtered_data


# ============================================================================
# Server Initialization
# ============================================================================

# Initialize environment and configuration
load_env_file()
API_KEY = os.getenv("DATA_GOV_API_KEY")
DATASET_REGISTRY = load_dataset_registry()

# Initialize semantic search if available
SEMANTIC_SEARCH_ENGINE = None
if SEMANTIC_SEARCH_AVAILABLE and DATASET_REGISTRY:
    try:
        print("🔄 Initializing semantic search...", file=sys.stderr)
        SEMANTIC_SEARCH_ENGINE = initialize_semantic_search(DATASET_REGISTRY)
        print("✅ Semantic search initialized", file=sys.stderr)
    except Exception as e:
        print(f"❌ Failed to initialize semantic search: {e}", file=sys.stderr)
        print("❌ Server requires semantic search to function properly", file=sys.stderr)
        # Don't exit here, let the tool function handle the error gracefully

# Create the FastMCP server instance
config = get_config()
mcp = FastMCP(
    name=config.server_name,
    mask_error_details=False,  # Prevent internal error details from leaking
    instructions="An MCP server for data.gov.in that provides semantic search and dataset access capabilities.",
)

# # Add middleware for better error handling and monitoring
# mcp.add_middleware(
#     ErrorHandlingMiddleware(
#         include_traceback=False,  # Don't include tracebacks in production
#         transform_errors=True,  # Transform errors to standard format
#     )
# )

# Add rate limiting middleware
mcp_server_config = config.get_section("mcp_server")
rate_limit_config = mcp_server_config.get("rate_limit", {}) if mcp_server_config else {}
mcp.add_middleware(
    SimpleRateLimiter(
        requests_per_minute=rate_limit_config.get("requests_per_minute", 60),
        burst_limit=rate_limit_config.get("burst_limit", 10),
    )
)

# HTTP middleware for browser clients
HTTP_MIDDLEWARE = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["mcp-session-id"],
    )
]

# Log initialization status
print("Creating MCP server...", file=sys.stderr)
if not API_KEY:
    print("⚠ WARNING: DATA_GOV_API_KEY environment variable not set", file=sys.stderr)
    print("Either set it as an environment variable or add it to a .env file", file=sys.stderr)
print(f"✓ Loaded {len(DATASET_REGISTRY)} datasets from registry", file=sys.stderr)

if SEMANTIC_SEARCH_ENGINE and SEMANTIC_SEARCH_ENGINE.is_ready():
    print("✅ Semantic search is ready for AI-powered dataset discovery", file=sys.stderr)
else:
    print("❌ Semantic search not available - server functionality will be limited", file=sys.stderr)
    if not SEMANTIC_SEARCH_AVAILABLE:
        print(
            "❌ Install semantic search packages: uv sync",
            file=sys.stderr,
        )
    else:
        print("❌ Run 'python build_embeddings.py' to build semantic search embeddings", file=sys.stderr)


# ============================================================================
# MCP Resources
# ============================================================================


@mcp.resource("dataset://registry")
async def get_dataset_registry() -> dict:
    """Expose the dataset registry as an MCP resource for metadata browsing."""
    try:
        if not DATASET_REGISTRY:
            raise ResourceError("Dataset registry not available or empty")

        # Return the full registry with enhanced metadata
        config = get_config()
        registry_with_metadata = {
            "total_datasets": len(DATASET_REGISTRY),
            "last_updated": config.get("mcp_server", "registry_last_updated", "2025-07-08"),
            "source": "data.gov.in API registry",
            "datasets": DATASET_REGISTRY,
            "sectors": list({d.get("sector", "Unknown") for d in DATASET_REGISTRY}),
            "ministries": list({d.get("ministry", "Unknown") for d in DATASET_REGISTRY}),
        }

        return registry_with_metadata
    except Exception as e:
        raise ResourceError(f"Error accessing registry: {str(e)}")


# ============================================================================
# MCP Tools
# ============================================================================


@mcp.tool()
async def search_datasets(
    queries: Annotated[
        List[str], Field(description="List of 1-5 search queries from general to specific", min_length=1, max_length=5)
    ],
    results_per_query: Annotated[
        Optional[int], Field(description="Results per query (default: 10)", ge=1, le=50)
    ] = None,
) -> dict:
    """
    Search datasets using multiple semantic queries simultaneously for comprehensive discovery.

    This approach allows finding both specific datasets and general datasets that can be filtered to get the specific data that is needed.
    Returns top results for each query, organized by search term for easy analysis.

    Args:
        queries: List of search queries from general to specific.
                Examples: ['flights', 'Air India flights', 'Delhi airport landings']
        results_per_query: Results per query (default: 10)

    Multi-Query Strategy:
        1. Think of 2-5 queries from general to specific
        2. Include both specific terms and filterable general terms
        3. Get top 10 results per query for focused analysis
        4. Low relevance results are automatically filtered out

    Example Usage:
        - User asks: "Air India flights landing in Delhi"
        - Queries: ['airline flights', 'Air India flights', 'Delhi airport data']
        - Returns: Top results for each, showing both specific datasets and filterable general ones
    """
    # Input validation using security utilities
    config = get_config()
    security_config = config.get_section("security") or {}

    try:
        queries = validate_query_list(
            queries,
            max_queries=security_config.get("max_queries", 5),
            max_query_length=security_config.get("max_query_length", 200),
        )
    except ValueError as e:
        log_security_event("input_validation_failed", {"error": str(e), "input": "queries"}, "WARNING")
        raise ValidationError(str(e))

    try:
        # Validate and limit queries
        if not queries:
            return {
                "error": "No queries provided. Please provide 1-5 search queries.",
                "example": "['flight data', 'Air India flights', 'Delhi airport']",
            }

        if len(queries) > config.max_queries_per_search:
            queries = queries[: config.max_queries_per_search]

        # Use config default if results_per_query not provided
        if results_per_query is None:
            results_per_query = config.results_per_query
        else:
            results_per_query = min(results_per_query, config.max_search_limit)

        # Check semantic search availability
        if not SEMANTIC_SEARCH_ENGINE or not SEMANTIC_SEARCH_ENGINE.is_ready():
            return {
                "error": "Semantic search not available",
                "suggestion": "Run 'python build_embeddings.py' to initialize semantic search",
            }

        # Execute searches for all queries
        all_results = {}
        total_found = 0

        for query in queries:
            # Perform semantic search for this query
            results = SEMANTIC_SEARCH_ENGINE.search(query, limit=results_per_query * 2)  # Get extra to filter

            if not results:
                all_results[query] = {"datasets": [], "found": 0, "note": "No matches found for this specific query"}
                continue

            # Filter results by minimum display similarity score
            filtered_results = [
                r for r in results if r.get("similarity_score", 0) >= config.min_display_similarity_score
            ]

            # Take top results_per_query after filtering
            top_results = filtered_results[:results_per_query]

            # Format results in compact form
            compact_results = []
            for result in top_results:
                desc = result.get("desc", "")
                preview = desc[:80] + "..." if len(desc) > 80 else desc

                compact_results.append(
                    {
                        "resource_id": result["resource_id"],
                        "title": result["title"],
                        "ministry": result.get("ministry", "Unknown"),
                        "sector": result.get("sector", "Unknown"),
                        "description_preview": preview,
                        "relevance_score": round(result.get("similarity_score", 0), 3),
                    }
                )

            all_results[query] = {
                "datasets": compact_results,
                "found": len(compact_results),
                "total_before_filtering": len(results),
                "filtered_out": len(results) - len(filtered_results) if len(results) > len(filtered_results) else 0,
            }

            total_found += len(compact_results)

        # Generate guidance for multi-query results
        guidance = _generate_multi_query_guidance(queries, all_results, config)

        return {
            "queries": queries,
            "results_by_query": all_results,
            "total_datasets_found": total_found,
            "search_strategy": "multi-query",
            "guidance": guidance,
        }

    except Exception as e:
        return {
            "error": f"Multi-query search failed: {str(e)}",
            "queries": queries if "queries" in locals() else [],
            "results_by_query": {},
        }


def _generate_multi_query_guidance(queries: List[str], results: Dict[str, Any], config: Any) -> Dict[str, Any]:
    """Generate guidance for multi-query search results."""
    total_datasets = sum(r.get("found", 0) for r in results.values())
    successful_queries = [q for q, r in results.items() if r.get("found", 0) > 0]

    guidance = {
        "summary": f"Searched {len(queries)} queries, found {total_datasets} total datasets across {len(successful_queries)} successful queries",
        "next_steps": [],
        "analysis_tips": [],
    }

    if total_datasets == 0:
        guidance["next_steps"].extend(
            [
                "No relevant datasets found across all queries",
                "Try broader domain terms or check spelling",
                "Consider searching for ministry/department names",
            ]
        )
    elif total_datasets >= config.guidance_high_result_threshold:
        guidance["next_steps"].extend(
            [
                "Excellent coverage! Multiple queries found relevant datasets",
                "🔴 FIRST: Inspect ALL promising datasets with inspect_dataset_structure() before downloads",
                "Compare results across queries to find both specific and general datasets",
                "Look for general datasets that can be filtered for specific needs",
            ]
        )
        if config.encourage_aggregation:
            guidance["next_steps"].append(
                "AFTER inspection: Consider combining insights from multiple queries and datasets"
            )
    else:
        guidance["next_steps"].extend(
            [
                "Good results found across queries",
                "🔴 FIRST: Inspect the most relevant datasets from each successful query",
                "Look for general datasets that might contain filterable data after inspection",
            ]
        )

    # Add MANDATORY next steps - inspection before ANY downloads
    if total_datasets > 0:
        guidance["next_steps"].extend(
            [
                "🔴 CRITICAL: You MUST inspect ALL promising datasets with inspect_dataset_structure() BEFORE any downloads",
                "🔴 DO NOT use download_dataset() or download_filtered_dataset() without inspection first",
                "⚠️  Inspection reveals data structure, columns, and filtering possibilities",
            ]
        )

    # Add query-specific analysis tips
    if len(successful_queries) > 1:
        guidance["analysis_tips"].extend(
            [
                "Compare datasets between queries - general vs specific coverage",
                "General datasets (from broad queries) may be filterable for specific needs",
                "Specific datasets (from narrow queries) may provide targeted data",
                "🔴 MANDATORY: Use inspect_dataset_structure() on ALL promising datasets from each query",
            ]
        )

    # Add specific resource suggestions
    promising_resources = []
    for query, result in results.items():
        datasets = result.get("datasets", [])
        if datasets:
            # Take top 1-2 from each successful query
            promising_resources.extend([d["resource_id"] for d in datasets[:2]])

    if promising_resources:
        guidance["start_with"] = promising_resources[:5]  # Limit to top 5 overall
        guidance["mandatory_first_step"] = (
            f"🔴 INSPECT THESE FIRST: {', '.join([f'inspect_dataset_structure(\"{r}\")' for r in promising_resources[:3]])}"
        )
        guidance["warning"] = "⚠️  DO NOT download any datasets without inspecting them first!"

    return guidance


@mcp.tool()
async def get_detailed_dataset_info(resource_ids: List[str]) -> dict:
    """
    Get detailed information for specific datasets identified from multi-query search.

    Use this after search_datasets() when you want complete details about specific promising datasets.

    Args:
        resource_ids: List of resource IDs to get detailed information for

    Returns:
        Detailed information including full descriptions for the specified datasets
    """
    try:
        if not resource_ids:
            return {
                "error": "No resource IDs provided",
                "usage": "Provide list of resource_ids from search_datasets() results",
            }

        if not SEMANTIC_SEARCH_ENGINE or not SEMANTIC_SEARCH_ENGINE.is_ready():
            return {
                "error": "Semantic search not available",
                "suggestion": "Run 'python build_embeddings.py' to initialize semantic search",
            }

        # Get detailed info for each resource ID from the registry
        detailed_datasets = []
        registry = DATASET_REGISTRY

        for resource_id in resource_ids:
            # Find the dataset in registry
            dataset = next((d for d in registry if d.get("resource_id") == resource_id), None)
            if dataset:
                detailed_datasets.append(dataset)
            else:
                detailed_datasets.append({"resource_id": resource_id, "error": "Dataset not found in registry"})

        return {
            "resource_ids": resource_ids,
            "datasets": detailed_datasets,
            "total_found": len([d for d in detailed_datasets if "error" not in d]),
        }

    except Exception as e:
        return {
            "error": f"Failed to get detailed dataset info: {str(e)}",
            "resource_ids": resource_ids if "resource_ids" in locals() else [],
        }


@mcp.tool()
async def download_dataset(resource_id: str, limit: Optional[int] = None) -> dict:
    """
    Download a complete dataset with automatic pagination in CSV format.

    ⚠️  PREREQUISITE: You MUST call inspect_dataset_structure() first to understand
    the dataset structure and determine if you need filtering!

    The server automatically handles pagination to download complete datasets up to 100,000 records.
    Uses intelligent pagination (1000 records per API call) to efficiently retrieve large datasets.

    Args:
        resource_id: The dataset resource ID (first inspect with inspect_dataset_structure()!)
        limit: Maximum number of records to return (uses config default: 1000 if None)

    Returns:
        Dict containing dataset records in CSV format (data_csv key) for easy analysis and export.

    Pagination Features:
        - Automatic server-side pagination handles datasets of any size
        - Downloads complete datasets up to 100,000 records total
        - Efficient chunked downloading (1000 records per API request)
        - No manual pagination needed - server handles it transparently

    Warning: This may return large amounts of data. Consider using download_filtered_dataset()
    with specific column filters to get only the data you need and avoid long responses.
    First inspect the dataset to understand if filtering would be beneficial!
    """
    # Input validation using security utilities
    try:
        resource_id = validate_resource_id(resource_id)
    except ValueError as e:
        log_security_event("input_validation_failed", {"error": str(e), "input": "resource_id"}, "WARNING")
        raise ValidationError(str(e))

    # Validate limit parameter
    if limit is not None:
        if not isinstance(limit, int):
            raise ValidationError("Limit must be an integer.")
        if limit <= 0:
            raise ValidationError("Limit must be a positive integer.")
        if limit > 100000:
            raise ValidationError("Limit cannot exceed 100,000 records.")

    try:
        if not API_KEY:
            raise ToolError("DATA_GOV_API_KEY environment variable not set. Please set it to use this tool.")

        # Use config default if limit not provided
        config = get_config()
        if limit is None:
            limit = config.download_limit

        result = await download_api(resource_id, API_KEY, limit)

        # Convert to CSV format and return only CSV
        if "records" in result and result["records"]:
            csv_data = convert_data_to_csv(result)
            # Keep metadata but replace records with CSV
            return {
                "data_csv": csv_data,
                "total": result.get("total", 0),
                "field": result.get("field", []),
                "message": f"Dataset downloaded successfully with {len(result.get('records', []))} records in CSV format",
            }
        else:
            return {"data_csv": "No data available", "total": 0, "message": "No records found"}

        return result
    except Exception as e:
        return {"error": f"Error downloading dataset: {str(e)}"}


@mcp.tool()
async def download_filtered_dataset(
    resource_id: str, column_filters: Union[str, Dict[str, str]], limit: Optional[int] = None
) -> dict:
    """
    Download a dataset with intelligent filtering and pagination in CSV format.

    ⚠️  PREREQUISITE: You MUST call inspect_dataset_structure() first to understand
    the dataset structure and available columns for filtering!

    This function downloads complete filtered datasets with automatic pagination and
    intelligent filtering capabilities.

    Args:
        resource_id: The dataset resource ID (first inspect with inspect_dataset_structure()!)
        column_filters: Column filters as JSON string (e.g., '{"state": "Maharashtra", "year": "2023"}')
                       or as a dictionary (e.g., {"state": "Maharashtra", "year": "2023"})
        limit: Maximum number of records to return in final result (default: 10,000)

    Returns:
        Dict containing filtered dataset records in CSV format (data_csv key) for easy analysis and export.

    Features:
        - Automatic pagination downloads complete datasets (up to 100,000 records)
        - Intelligent filtering capabilities
        - Returns data in CSV format for easy analysis
        - No manual pagination handling needed

    Example: Even if a dataset has 50,000 records and your filter matches 15,000 records,
    the server will automatically handle all data retrieval and return your filtered results.
    """
    try:
        if not API_KEY:
            return {"error": "DATA_GOV_API_KEY environment variable not set. Please set it to use this tool."}

        config = get_config()
        max_result_limit = limit or config.get("data_api", "max_download_limit")

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
                + 'Expected JSON string like "{"column_name": "filter_value"}" or a dictionary object.'
            }

        # Get dataset metadata to determine filterable fields
        metadata = await get_dataset_metadata(resource_id, API_KEY)
        field_exposed = metadata.get("field_exposed", [])

        # Build server-side and client-side filters
        server_filters, client_filters = build_server_side_filters(filters_dict, field_exposed)

        # Download data with server-side filtering and pagination
        if server_filters or not filters_dict:
            # Use server-side filtering and pagination
            result = await download_api_paginated(
                resource_id, API_KEY, server_filters, max_records=config.get("data_api", "max_total_records")
            )
        else:
            # No server-side filters possible, use legacy method
            result = await download_api(resource_id, API_KEY, config.get("data_api", "max_download_limit"))

        total_records = len(result.get("records", []))
        total_available = result.get("total", total_records)

        # Apply client-side filtering if needed
        if client_filters:
            result = filter_dataset_records(result, client_filters)
            filtered_count = len(result.get("records", []))
        else:
            filtered_count = total_records

        # Add filtering summary
        result["applied_filters"] = filters_dict
        result["filtering_summary"] = {
            "total_records_in_dataset": total_available,
            "records_after_filtering": filtered_count,
            "filter_criteria": filters_dict,
        }

        # Handle large filtered results
        if filtered_count > max_result_limit:
            # Provide sample and guidance for further filtering
            sample_records = result["records"][:10]

            # Analyze the filtered data to suggest additional filters
            additional_filter_suggestions = {}
            for record in sample_records:
                for key, value in record.items():
                    if key not in filters_dict and isinstance(value, str) and len(value) < 50:
                        if key not in additional_filter_suggestions:
                            additional_filter_suggestions[key] = set()
                        additional_filter_suggestions[key].add(value)

            # Convert sets to lists and limit suggestions
            for key in additional_filter_suggestions:
                additional_filter_suggestions[key] = list(additional_filter_suggestions[key])[:5]

            return {
                "status": "filtered_dataset_too_large",
                "total_records_in_dataset": total_available,
                "records_after_filtering": filtered_count,
                "max_result_limit": max_result_limit,
                "applied_filters": filters_dict,
                "filtering_summary": result["filtering_summary"],
                "message": f"Filtered dataset has {filtered_count} records, which exceeds the limit of {max_result_limit}.",
                "sample_records_csv": (
                    convert_data_to_csv({"records": sample_records}) if sample_records else "No sample data available"
                ),
                "suggested_additional_filters": additional_filter_suggestions,
                "guidance": f"Please add more specific filters to reduce the result set below {max_result_limit} records. Use the suggested_additional_filters to see available values for additional filtering.",
                "action_required": "Add more specific column filters to reduce the dataset size.",
            }

        # Add informative note about applied filters
        result["note"] = (
            f"Dataset filtered using: {', '.join(f'{k}={v}' for k, v in filters_dict.items())}"
            if filters_dict
            else "No filters applied"
        )

        # Convert to CSV format and return only CSV
        if "records" in result and result["records"]:
            csv_data = convert_data_to_csv(result)
            # Keep important metadata but replace records with CSV
            return {
                "data_csv": csv_data,
                "total": result.get("total", 0),
                "applied_filters": result["applied_filters"],
                "filtering_summary": result["filtering_summary"],
                "note": result["note"],
                "message": f"Filtered dataset with {len(result.get('records', []))} records in CSV format",
            }
        else:
            return {
                "data_csv": "No data available after filtering",
                "applied_filters": result.get("applied_filters", {}),
                "filtering_summary": result.get("filtering_summary", {}),
                "message": "No records found after applying filters",
            }

        return result

    except Exception as e:
        return {"error": f"Error downloading filtered dataset: {str(e)}"}


@mcp.tool()
async def inspect_dataset_structure(resource_id: str, sample_size: Optional[int] = None) -> dict:
    """
    🔴 MANDATORY: Dataset structure inspection - REQUIRED before any downloads!

    Shows a small sample of records from what could be a much larger dataset. You MUST
    call this tool before using download_dataset() or download_filtered_dataset().

    This inspection reveals:
    - Available columns and data types
    - Sample data values for understanding content in CSV format
    - Filtering possibilities for large datasets
    - Data quality and completeness

    Args:
        resource_id: The dataset resource ID
        sample_size: Number of sample records to return (default: 3 for quick inspection)

    Returns:
        Dict containing dataset structure info including sample_records_csv (CSV format)
        for easy data analysis.

    Critical Note: This shows only a sample for inspection. After inspection, use
    download_filtered_dataset() to get the complete dataset in CSV format with automatic
    data retrieval for potentially thousands or tens of thousands of records.

    ⚠️  WARNING: Do NOT download datasets without inspecting them first! You'll miss
    important filtering opportunities and may download unnecessary data.
    """
    try:
        if not API_KEY:
            return {"error": "DATA_GOV_API_KEY environment variable not set. Please set it to use this tool."}

        # Use config default if sample_size not provided
        config = get_config()
        if sample_size is None:
            sample_size = config.inspect_sample_size

        # Download a small sample to inspect structure
        result = await download_api(resource_id, API_KEY, sample_size)

        # Extract structure info with enhanced guidance
        fields = result.get("field", [])
        sample_records = result.get("records", [])[:sample_size]

        # Extract column names for easier reference
        column_names = [
            field.get("id", field.get("name", "")) for field in fields if field.get("id") or field.get("name")
        ]

        # Create field name mapping guide for better filtering
        field_name_guide = {}
        for field in fields:
            field_id = field.get("id", "")
            field_name = field.get("name", "")
            field_type = field.get("type", "")

            if field_id and field_name:
                field_name_guide[field_name] = {
                    "use_in_filters": field_id,  # What to actually use in filters
                    "display_name": field_name,
                    "type": field_type,
                }

        # Create CSV format for sample data
        sample_csv = convert_data_to_csv({"records": sample_records}) if sample_records else "No sample data available"

        structure = {
            "fields": fields,
            "column_names": column_names,
            "field_filtering_guide": field_name_guide,
            "sample_records_csv": sample_csv,
            "total_records_available": result.get("total", "unknown"),
            "sample_size_shown": len(sample_records),
            "usage_tip": "Use download_filtered_dataset() for complete data in CSV format with intelligent filtering",
            "field_name_tips": {
                "flexible_naming": "You can use either display names (e.g., 'Arrival_Date') or field IDs (e.g., 'arrival_date')",
                "case_insensitive": "Field name matching is case-insensitive",
                "date_filtering": "For date fields, use exact format as shown in sample CSV data (e.g., '16/07/2025')",
            },
            "example_filter": (
                f'{{"column_name": "filter_value"}} or as dict {{"column_name": "filter_value"}}'
                if column_names
                else "No columns available for filtering"
            ),
        }

        return structure
    except Exception as e:
        return {"error": f"Error inspecting dataset: {str(e)}"}


@mcp.tool()
async def get_registry_summary() -> dict:
    """Get a summary of the dataset registry including counts by sector and ministry."""
    try:
        # Count datasets by sector and ministry
        sector_counts = {}
        ministry_counts = {}

        for dataset in DATASET_REGISTRY:
            sector = dataset.get("sector", "Unknown")
            ministry = dataset.get("ministry", "Unknown")

            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            ministry_counts[ministry] = ministry_counts.get(ministry, 0) + 1

        return {
            "total_datasets": len(DATASET_REGISTRY),
            "sectors_count": len(sector_counts),
            "ministries_count": len(ministry_counts),
            "datasets_by_sector": dict(sorted(sector_counts.items(), key=lambda x: x[1], reverse=True)),
            "top_ministries": dict(sorted(ministry_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            "note": "Use list_sectors() to see all sectors, or search_datasets() to find specific datasets",
        }
    except Exception as e:
        return {"error": f"Error getting registry summary: {str(e)}"}


@mcp.tool()
async def list_sectors() -> dict:
    """List all available sectors in the registry."""
    try:
        sectors = {dataset.get("sector", "Unknown") for dataset in DATASET_REGISTRY}
        sorted_sectors = sorted(list(sectors))

        return {
            "total_sectors": len(sorted_sectors),
            "sectors": sorted_sectors,
            "note": "Use search_datasets() with sector names to find datasets in specific sectors",
        }
    except Exception as e:
        return {"error": f"Error listing sectors: {str(e)}"}


@mcp.tool()
async def plan_multi_dataset_analysis(search_results: List[str], query_context: str) -> dict:
    """
    Plan a comprehensive analysis workflow using multiple datasets.

    Args:
        search_results: List of resource_ids from search_datasets results
        query_context: The original user query or analysis goal

    This tool helps organize a systematic approach to analyzing multiple datasets
    and ensures comprehensive coverage of all relevant data sources.
    """
    try:
        if not search_results:
            return {"error": "No resource IDs provided for analysis planning"}

        # Find dataset metadata for the provided resource IDs
        relevant_datasets = []
        for resource_id in search_results:
            for dataset in DATASET_REGISTRY:
                if dataset.get("resource_id") == resource_id:
                    relevant_datasets.append(dataset)
                    break

        if not relevant_datasets:
            return {"error": "None of the provided resource IDs found in registry"}

        # Create analysis plan
        analysis_plan = {
            "query_context": query_context,
            "total_datasets_to_analyze": len(relevant_datasets),
            "critical_requirement": "🔴 You MUST execute ALL Phase 1 inspection calls before ANY Phase 2 downloads!",
            "systematic_workflow": [
                "Phase 1: MANDATORY Structure Inspection (MUST complete ALL before Phase 2)",
                "Phase 2: Strategic Data Collection (ONLY after Phase 1 complete)",
                "Phase 3: Cross-Dataset Analysis",
                "Phase 4: Comprehensive Synthesis",
            ],
            "phase_1_inspect_calls": [f"inspect_dataset_structure('{d['resource_id']}')" for d in relevant_datasets],
            "phase_1_warning": "⚠️  Do NOT proceed to Phase 2 without completing ALL inspections!",
            "phase_2_download_calls": [
                f"download_filtered_dataset('{d['resource_id']}', relevant_filters_from_inspection)"
                for d in relevant_datasets
            ],
            "datasets_overview": [
                {
                    "resource_id": d["resource_id"],
                    "title": d.get("title", "Unknown"),
                    "sector": d.get("sector", "Unknown"),
                    "ministry": d.get("ministry", "Unknown"),
                    "expected_contribution": f"Sector: {d.get('sector', 'Unknown')} data for {query_context}",
                }
                for d in relevant_datasets
            ],
            "analysis_strategy": (
                f"🔴 MANDATORY: Execute ALL Phase 1 inspection calls to understand data structures, "
                f"ONLY THEN execute Phase 2 download calls with informed filtering strategies, "
                f"finally synthesize insights from all {len(relevant_datasets)} datasets "
                f"to provide comprehensive analysis of: {query_context}"
            ),
            "success_criteria": f"Final answer incorporates findings from all {len(relevant_datasets)} datasets with proper inspection workflow",
        }

        return analysis_plan

    except Exception as e:
        return {"error": f"Error creating analysis plan: {str(e)}"}


@mcp.tool()
async def update_config(section: str, key: str, value: Any) -> dict:
    """
    Update a configuration value and save to file.

    Args:
        section: Configuration section (e.g., 'semantic_search', 'data_api')
        key: Configuration key to update
        value: New value to set

    Common configurable parameters:
    - semantic_search.default_search_limit: Number of datasets to return (default: 20)
    - semantic_search.relevance_threshold: Minimum similarity score
    - data_api.default_download_limit: Default dataset download limit (default: 100)
    - data_api.default_inspect_sample_size: Sample size for inspection (default: 3)
    """
    try:
        config = get_config()
        old_value = config.get(section, key, None)

        config.set(section, key, value)
        config.save()

        return {
            "status": "success",
            "section": section,
            "key": key,
            "old_value": old_value,
            "new_value": value,
            "message": f"Updated {section}.{key} from {old_value} to {value}",
        }
    except Exception as e:
        return {"error": f"Failed to update config: {str(e)}"}


@mcp.tool()
async def get_search_guidance() -> dict:
    """
    Get comprehensive guidance for the multi-query search strategy.

    Emphasizes using multiple queries simultaneously to find both specific and general datasets.
    """
    config = get_config()

    guidance_content = {
        "multi_query_search_strategy": {
            "step_1": {
                "title": "Think Multiple Queries Simultaneously",
                "description": "Create 2-5 queries from general to specific to capture all relevant datasets",
                "examples": [
                    "User asks: 'Air India flights landing in Delhi'",
                    "Queries: ['flight data', 'airline flights', 'Air India flights', 'Delhi airport data']",
                    "Result: Find both general flight datasets (filterable) and specific Air India datasets",
                ],
                "query_strategy": [
                    "Start with broad domain terms: 'flight data', 'agriculture data'",
                    "Add medium specificity: 'airline flights', 'crop production'",
                    "Include specific terms: 'Air India flights', 'wheat production Maharashtra'",
                ],
                "tip": f"Each query returns top {config.results_per_query} most relevant results",
            },
            "step_2": {
                "title": "Analyze Results Across Queries",
                "description": "Compare results to identify both specific datasets and general filterable ones",
                "actions": [
                    "Review results from each query separately",
                    "Look for general datasets that appear in broad queries",
                    "Identify specific datasets that appear in narrow queries",
                    "Note which datasets appear across multiple queries (high relevance)",
                ],
                "filtering_insight": [
                    "General datasets from broad queries can often be filtered for specific needs",
                    "Specific datasets provide targeted data but may have limited scope",
                    "Cross-query appearance indicates high relevance to your topic",
                ],
            },
            "step_3": {
                "title": "🔴 MANDATORY: Inspect Dataset Structures BEFORE Any Downloads",
                "description": "You MUST inspect ALL promising datasets before downloading - this is not optional",
                "critical_requirement": [
                    "🔴 NEVER use download_dataset() or download_filtered_dataset() without inspect_dataset_structure() first",
                    "🔴 Inspection is MANDATORY for understanding data structure and filtering possibilities",
                    "🔴 Downloading without inspection wastes resources and provides incomplete analysis",
                ],
                "benefits": [
                    "Understand which general datasets can be filtered for specific needs",
                    "Identify unique data available in specific datasets",
                    "Plan combination strategies across dataset types",
                    "Assess data quality and completeness",
                    "Determine optimal filtering criteria for large datasets",
                ],
                "priority_order": [
                    "First: Datasets that appear in multiple queries",
                    "Second: General datasets from broad queries (for filtering potential)",
                    "Third: Specific datasets from narrow queries (for targeted data)",
                ],
                "workflow": [
                    "1. Call inspect_dataset_structure() for ALL promising datasets",
                    "2. ONLY AFTER inspection, plan your download strategy",
                    "3. Use insights from inspection to determine optimal filters",
                    "4. Then proceed with download_dataset() or download_filtered_dataset()",
                ],
            },
            "step_4": {
                "title": "Download and Combine Strategically (AFTER Inspection)",
                "description": "Extract data optimally from both general and specific datasets using inspection insights",
                "prerequisites": [
                    "✅ ALL target datasets have been inspected with inspect_dataset_structure()",
                    "✅ Data structures and columns are understood",
                    "✅ Filtering strategies have been planned based on inspection",
                ],
                "strategies": [
                    "Filter general datasets for specific criteria using columns identified in inspection",
                    "Download specific datasets for targeted insights with known structure",
                    "Combine filtered general data with specific data for comprehensive analysis",
                    "Cross-validate findings across different dataset types using common columns",
                ],
            },
        },
        "data_download_capabilities": {
            "automatic_pagination": [
                "Server handles pagination transparently - no manual offset/limit needed",
                "Downloads complete datasets up to 100,000 records automatically",
                "Uses efficient chunked downloading (1000 records per API call)",
                "Works seamlessly with both filtered and unfiltered downloads",
            ],
            "filtering_with_pagination": [
                "Server-side filtering reduces data transfer (applied during pagination)",
                "Client-side filtering works on complete paginated datasets",
                "Hybrid approach maximizes efficiency for large datasets",
                "Example: Filter 50,000-record dataset for specific state/year efficiently",
            ],
            "large_dataset_handling": [
                "No size limits - server automatically paginates through any dataset size",
                "Get complete filtered results without worrying about API pagination",
                "Perfect for comprehensive analysis of government datasets",
                "Handles datasets ranging from hundreds to tens of thousands of records",
            ],
        },
        "multi_query_best_practices": {
            "effective_query_combinations": [
                "Domain + Specific: ['transport data', 'railway transport', 'Delhi Metro']",
                "General + Filtered: ['hospital data', 'government hospitals', 'Delhi hospitals']",
                "Temporal + Geographic: ['economic data', 'state GDP', 'Maharashtra economy']",
                "Entity + Location: ['education data', 'school data', 'Delhi schools']",
            ],
            "query_progression_examples": [
                "Agriculture: ['agriculture', 'crop data', 'wheat production', 'Maharashtra wheat']",
                "Healthcare: ['health data', 'medical statistics', 'hospital capacity', 'COVID statistics']",
                "Transport: ['transport', 'aviation data', 'airport statistics', 'Delhi airport traffic']",
            ],
            "avoid_redundant_queries": [
                "Don't repeat similar terms: ['flights', 'flight data'] → just use 'flight data'",
                "Progress from broad to specific systematically",
                "Include geographic and entity variations when relevant",
            ],
        },
        "result_interpretation": {
            "general_vs_specific_datasets": [
                "General datasets: Broad coverage, require filtering, appear in broad queries",
                "Specific datasets: Targeted data, ready to use, appear in specific queries",
                "Best approach: Use both types for comprehensive analysis",
            ],
            "similarity_score_guidance": [
                f"Scores below {config.min_display_similarity_score} are automatically filtered out",
                "Higher scores (>0.4) indicate strong relevance",
                "Cross-query appearances suggest high overall relevance",
            ],
            "dataset_prioritization": [
                "Priority 1: Datasets appearing in multiple queries",
                "Priority 2: High-scoring general datasets (filterable)",
                "Priority 3: High-scoring specific datasets (targeted)",
            ],
        },
        "example_comprehensive_workflow": {
            "description": "Multi-query search with MANDATORY inspection before downloads",
            "user_question": "What is the trend in renewable energy adoption across Indian states?",
            "queries": [
                "energy data",
                "renewable energy",
                "solar power India",
                "wind power statistics",
                "state energy statistics",
            ],
            "expected_outcome": "Find both general energy datasets (filterable by renewable/state) and specific renewable energy datasets",
            "mandatory_steps": [
                "1. Run multi-query search to find datasets",
                "2. 🔴 MANDATORY: inspect_dataset_structure() on ALL promising datasets",
                "3. ONLY AFTER inspection: Plan filtering and download strategy",
                "4. Execute downloads with optimal filters based on inspection",
            ],
            "analysis_steps": [
                "🔴 FIRST: Inspect general 'energy data' results to understand filterable columns",
                "🔴 FIRST: Inspect specific 'renewable energy' datasets to understand structure",
                "Cross-reference state-wise data capabilities across inspected datasets",
                "AFTER inspection: Download filtered general data with specific renewable data",
            ],
            "critical_warning": "⚠️  NEVER download without inspection - you'll miss filtering opportunities and waste resources",
        },
        "workflow_philosophy": f"Think multiple angles → search simultaneously → 🔴 INSPECT ALL promising datasets → download strategically. Each query finds top {config.results_per_query} results. NEVER download without inspection first.",
    }

    return guidance_content


@mcp.tool()
async def get_current_config() -> dict:
    """Get the current configuration settings."""
    try:
        config = get_config()
        return {
            "semantic_search": config.get_section("semantic_search"),
            "data_api": config.get_section("data_api"),
            "mcp_server": config.get_section("mcp_server"),
            "analysis": config.get_section("analysis"),
            "config_file_path": str(config.config_path),
        }
    except Exception as e:
        return {"error": f"Failed to get config: {str(e)}"}


# ============================================================================
# Main Entry Point
# ============================================================================


def main() -> None:
    """Run the MCP server."""
    print("Starting MCP server with semantic search...", file=sys.stderr)

    transport = os.getenv("MCP_TRANSPORT", os.getenv("FASTMCP_TRANSPORT", "streamable-http")).strip().lower()
    if transport == "http":
        # Backward-compatible alias that uses FastMCP streamable HTTP transport.
        transport = "streamable-http"

    if transport not in {"stdio", "streamable-http"}:
        print(
            f"⚠ WARNING: Unsupported transport '{transport}'. Falling back to 'streamable-http'.",
            file=sys.stderr,
        )
        transport = "streamable-http"

    if not API_KEY:
        print("⚠ WARNING: DATA_GOV_API_KEY environment variable not set", file=sys.stderr)
        print("Set DATA_GOV_API_KEY=<your_api_key> for full functionality", file=sys.stderr)
    else:
        print("✓ DATA_GOV_API_KEY is configured", file=sys.stderr)

    # Check semantic search status
    if SEMANTIC_SEARCH_ENGINE and SEMANTIC_SEARCH_ENGINE.is_ready():
        print("✅ Semantic search is ready for AI-powered dataset discovery", file=sys.stderr)
    elif SEMANTIC_SEARCH_AVAILABLE:
        print("❌ Semantic search packages available but not initialized", file=sys.stderr)
        print("❌ Run 'python build_embeddings.py' to build embeddings", file=sys.stderr)
    else:
        print("❌ Semantic search packages not installed", file=sys.stderr)
        print("❌ Install with: uv sync", file=sys.stderr)

    if transport == "stdio":
        print("Starting stdio transport...", file=sys.stderr)
        mcp.run(transport="stdio")
        return

    host = os.getenv("FASTMCP_HOST", "127.0.0.1")
    port = int(os.getenv("FASTMCP_PORT", "8000"))
    path = os.getenv("FASTMCP_STREAMABLE_HTTP_PATH", "/mcp")

    print(f"Starting Streamable HTTP transport on http://{host}:{port}{path}", file=sys.stderr)
    mcp.run(
        transport="streamable-http",
        host=host,
        port=port,
        path=path,
        middleware=HTTP_MIDDLEWARE,
    )



if __name__ == "__main__":
    print("Script starting...", file=sys.stderr)
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc(file=sys.stderr)
