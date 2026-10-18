# MCP Server: data.gov.in

A clean, production-ready MCP server for analyzing Indian government datasets on data.gov.in. Provides AI models like Claude/Gemini/ChatGPT/Llama/Deepseek with intelligent access to 
data.gov.in through **AI-powered semantic search** capabilities as well as downstream retrieval and processing.

Note: The semantic search relies on a metadata registry, which needs to be scraped periodically. I have a whole pipeline for parallelized building of the data.gov.in metadata registry which I'm not making public. Without that script, newer datasets will not be reflected in the semantic search. However, you can still provide the MCP client with the resource ID of any dataset newly uploaded to data.gov.in and it will be able to fetch it and process it. If you are interested in a use case that requires the dataset registry to be up-to-date, please contact me.

## 🚀 Quick Start

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Download model and precompute embeddings:**
   ```bash
   # Download the sentence transformer model locally (self-contained)
   uv run download_model.py
   
   # Build embeddings for semantic search
   uv run build_embeddings.py
   
   # Or run the complete setup script
   uv run setup.py
   ```
   This downloads the all-MiniLM-L6-v2 model to the `models/` directory and creates embeddings for all datasets.

3. **Get API Key:**
   - Sign up at [data.gov.in](https://data.gov.in/)
   - Get your API key from your profile
   - Set it as environment variable: `export DATA_GOV_API_KEY=your_api_key_here`
   - Or create a `.env` file with: `DATA_GOV_API_KEY=your_api_key_here`

4. **Choose transport mode:**
   - `stdio` for local MCP clients like Claude Desktop
   - `streamable-http` for browser/remote HTTP MCP clients

5. **Configure Claude Desktop (stdio mode):**
   Add to `claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "data-gov-in": {
         "command": "uv",
         "args": ["run", "mcp_server.py"],
          "cwd": "<path_to_project>",
          "env": {
            "MCP_TRANSPORT": "stdio"
          }
       }
     }
   }
   ```

6. **Run with Streamable HTTP (optional):**
   ```bash
   MCP_TRANSPORT=streamable-http \
   FASTMCP_HOST=127.0.0.1 \
   FASTMCP_PORT=8000 \
   FASTMCP_STREAMABLE_HTTP_PATH=/mcp \
   uv run mcp_server.py
   ```
   Endpoint: `http://127.0.0.1:8000/mcp`

7. **Restart your MCP client and test:**
   ```
   "Search for healthcare datasets in India and show me regional patterns in them."
   ```

## 🚚 Transport Toggle

The server now supports runtime transport switching using environment variables.

- `MCP_TRANSPORT`: `stdio` or `streamable-http` (default: `streamable-http`)
- `FASTMCP_TRANSPORT`: optional fallback if `MCP_TRANSPORT` is unset
- `FASTMCP_HOST`: HTTP bind host (default: `127.0.0.1`)
- `FASTMCP_PORT`: HTTP bind port (default: `8000`)
- `FASTMCP_STREAMABLE_HTTP_PATH`: HTTP MCP path (default: `/mcp`)

Examples:

```bash
# Local stdio mode
MCP_TRANSPORT=stdio uv run mcp_server.py

# Streamable HTTP mode
MCP_TRANSPORT=streamable-http uv run mcp_server.py
```

## 🎯 Key Features

- **AI-Powered Semantic Search**: Uses all-MiniLM-L6-v2 and FAISS for intelligent dataset discovery
- **Multi-Query Search**: Simultaneous search with multiple queries to find both specific and general filterable datasets
- **Automatic Server-Side Pagination**: Downloads complete datasets up to 100,000 records without manual pagination
- **Intelligent Hybrid Filtering**: Server-side filtering (faster) + client-side filtering (comprehensive) with full pagination
- **Precomputed Embeddings**: Fast search with model preloading for optimal performance
- **8 Core Tools**: Multi-query search, download, filter, inspect, plan, summarize, and browse datasets
- **Production Security**: Input validation, error masking, rate limiting, and audit logging

## 🔍 **Multi-Query Search Strategy**

The MCP server uses a **multi-query search approach** that finds both specific datasets and general filterable datasets simultaneously:

### **1. Think Multiple Queries Simultaneously**
```
search_datasets(['flight data', 'airline flights', 'Air India flights', 'Delhi airport data'])
→ Top 10 results per query → Comprehensive coverage of specific + general datasets
→ 🔴 MANDATORY: inspect_dataset_structure() on ALL promising datasets → understand structure and filtering options
→ download_filtered_dataset() strategically → combine specific and filtered general data (ONLY after inspection)
```

### **2. Multi-Query Philosophy**
- **Broad to Specific Coverage**: "flight data" finds general datasets, "Air India flights" finds specific ones
- **Filterable General Data**: General datasets from broad queries can be filtered for specific needs
- **Comprehensive Discovery**: Each query returns top 10 most relevant results
- **Low Relevance Filtering**: Results below similarity threshold automatically filtered out

### **3. Strategic Query Design**
- **Domain Level**: "agriculture data", "transport data", "health statistics"
- **Medium Specificity**: "crop production", "airline flights", "hospital data"  
- **High Specificity**: "wheat production Maharashtra", "Air India flights", "Delhi hospitals"
- **Geographic/Entity**: Include location and organization terms when relevant

### **4. Smart Result Analysis**
- **Cross-Query Relevance**: Datasets appearing in multiple queries are highly relevant
- **General vs Specific**: Compare broad query results (filterable) with specific query results (targeted)
- **Ministry Diversity**: Results span multiple government departments for comprehensive coverage

### **Example Multi-Query Workflow**
```
User: "Air India flights landing in Delhi airport"
→ search_datasets(['flight data', 'airline flights', 'Air India flights', 'Delhi airport data'])
→ Results: General flight datasets (filter for Air India + Delhi) + specific Air India datasets
→ 🔴 MANDATORY: inspect_dataset_structure() on ALL promising datasets BEFORE any downloads
→ Strategy: After inspection, filter general "all flights" dataset for Air India + Delhi, combine with specific Air India data
```

**Core Principle**: Multiple angles → simultaneous search → 🔴 **MANDATORY INSPECTION** → strategic downloads!

## 📊 Available Tools

1. **`search_datasets`** - Multi-query semantic search with 2-5 queries simultaneously (10 results per query)
2. **`get_detailed_dataset_info`** - Get complete information for specific datasets by resource ID
3. **`get_search_guidance`** - Comprehensive guide for multi-query search strategy and pagination capabilities
4. **`download_dataset`** - Download complete datasets with automatic pagination (⚠️ **REQUIRES INSPECTION FIRST**)
5. **`download_filtered_dataset`** - Download datasets with intelligent hybrid filtering (⚠️ **REQUIRES INSPECTION FIRST**)
6. **🔴 `inspect_dataset_structure`** - **MANDATORY** before downloads: Examine dataset schema, sample records, and pagination info
7. **`plan_multi_dataset_analysis`** - Plan comprehensive analysis workflows across multiple datasets
8. **`get_registry_summary`** - Get overview of available datasets by sector/ministry
9. **`list_sectors`** - List all available data sectors

## ⚙️ Configuration

The server uses a `config.json` file for easily adjustable parameters. Key settings include:

### Semantic Search Parameters
- `model_name`: Sentence transformer model to use
- `results_per_query`: Number of results per query in multi-query search (default: 10)
- `max_queries_per_search`: Maximum queries allowed per search (default: 5)
- `min_similarity_score`: Minimum similarity score for search engine
- `min_display_similarity_score`: Minimum score to display to users (default: 0.15)
- `title_weight`: How much to weight dataset titles in search
- `guidance_high_result_threshold`: Threshold for encouraging aggregation (default: 25)
- `guidance_medium_result_threshold`: Threshold for medium result guidance (default: 10)
- `encourage_aggregation`: Enable multi-dataset aggregation guidance (default: true)
- `emphasize_multi_query_search`: Emphasize multi-query search approach (default: true)

### Data API Parameters
- `default_download_limit`: Default number of records to download
- `max_download_limit`: Maximum allowed download limit
- `default_inspect_sample_size`: Sample size for dataset inspection
- `request_timeout`: API request timeout in seconds

### Analysis Parameters
- `high_relevance_threshold`: Threshold for high relevance datasets
