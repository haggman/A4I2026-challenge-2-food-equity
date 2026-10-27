"""Person A — Google-Managed BigQuery MCP & GenAI MCP Toolbox Integration (`agent/mcp_config.py`).

Provides `get_mcp_toolsets() -> list` consumed by Person B's `agent/agent.py`.
Supports three enterprise BigQuery MCP modes with automatic pre-flight health checks so the
ADK agent never crashes if an external MCP server is not yet running:

1. **Google-Managed Remote BigQuery MCP Server** (`https://bigquery.googleapis.com/mcp`)
   Authenticated via Application Default Credentials (`google.auth.default()`) Bearer token
   and `x-goog-user-project` header.
2. **GenAI MCP Toolbox for Databases** (`MCP_TOOLBOX_URL`, configured via `agent/tools.yaml`)
   Connects over SSE/HTTP to a local or Cloud Run `toolbox` instance exposing parameterized
   BigQuery tools for `a4i_food`.
3. **Graceful Fallback (`[]`)**
   If neither endpoint is reachable or enabled, logs a non-fatal diagnostic and returns `[]`
   so the core Python BigQuery tools in `agent/tools.py` continue to operate without interruption.
"""

from __future__ import annotations

import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import google.auth
import google.auth.transport.requests

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-04-ef48e08bc216")
DATASET = os.environ.get("BIGQUERY_DATASET", "a4i_food")
MANAGED_BQ_MCP_URL = "https://bigquery.googleapis.com/mcp"
TOOLS_YAML_PATH = Path(__file__).resolve().parent / "tools.yaml"


def _get_gcp_Access_headers() -> dict[str, str]:
    """Obtain OAuth2 Bearer token headers using Google Application Default Credentials."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT_ID)
    credentials, detected_project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_req = google.auth.transport.requests.Request()
    credentials.refresh(auth_req)
    active_project = project or detected_project or PROJECT_ID
    return {
        "Authorization": f"Bearer {credentials.token}",
        "x-goog-user-project": active_project,
    }


def _is_url_reachable(url: str, headers: dict[str, str] | None = None, timeout: float = 2.0) -> bool:
    """Perform a fast pre-flight check so an unreachable MCP server never hangs ADK startup."""
    try:
        req = urllib.request.Request(url, headers=headers or {}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 500
    except urllib.error.HTTPError as http_err:
        # HTTP 400/405 on an MCP POST/SSE endpoint means the server is alive and listening!
        return http_err.code in (200, 204, 400, 401, 403, 405, 406)
    except Exception:
        return False


def _build_toolbox_mcp_toolset(toolbox_url: str) -> Any | None:
    """Connect to a GenAI MCP Toolbox for Databases server (`agent/tools.yaml`)."""
    try:
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import SseConnectionParams
    except ImportError:
        try:
            from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, SseServerParams as SseConnectionParams  # type: ignore
        except ImportError as exc:
            logger.warning("google-adk MCP classes not available: %s", exc)
            return None

    sse_url = toolbox_url.rstrip("/")
    if not sse_url.endswith("/sse"):
        sse_url = f"{sse_url}/sse"

    if not _is_url_reachable(sse_url, timeout=1.5):
        logger.info("MCP Toolbox URL %s is not currently reachable; skipping.", sse_url)
        return None

    logger.info("Attaching GenAI MCP Toolbox toolset from %s", sse_url)
    return McpToolset(connection_params=SseConnectionParams(url=sse_url))


def _build_managed_bigquery_mcp_toolset(mcp_url: str) -> Any | None:
    """Connect to the Google-Managed BigQuery MCP Server (`https://bigquery.googleapis.com/mcp`)."""
    try:
        headers = _get_gcp_Access_headers()
    except Exception as exc:
        logger.warning("Could not obtain GCP credentials for Managed BigQuery MCP: %s", exc)
        return None

    if not _is_url_reachable(mcp_url, headers=headers, timeout=2.0):
        logger.info("Managed BigQuery MCP endpoint (%s) not reachable; skipping.", mcp_url)
        return None

    try:
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
        from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

        logger.info("Attaching Google-Managed BigQuery MCP Server (%s)", mcp_url)
        return McpToolset(
            connection_params=StreamableHTTPConnectionParams(
                url=mcp_url,
                headers=headers,
            )
        )
    except ImportError as exc:
        logger.warning("StreamableHTTPConnectionParams not available in installed google-adk: %s", exc)
        return None


def get_mcp_toolsets() -> list[Any]:
    """Return configured BigQuery MCP toolsets for Person B's ADK `Agent`.

    Environment variables supported:
    - `MCP_TOOLBOX_URL`: URL of a running GenAI MCP Toolbox server (e.g. `http://127.0.0.1:5000`).
    - `MCP_SERVER_URL`: Explicit Streamable HTTP MCP URL (e.g. `https://bigquery.googleapis.com/mcp`).
    - `ENABLE_MANAGED_BQ_MCP`: Set to `'true'` to auto-connect to `https://bigquery.googleapis.com/mcp`
      using Application Default Credentials.
    """
    toolsets: list[Any] = []

    # 1. Check GenAI MCP Toolbox (`MCP_TOOLBOX_URL`)
    toolbox_url = os.environ.get("MCP_TOOLBOX_URL", "").strip()
    if toolbox_url:
        ts = _build_toolbox_mcp_toolset(toolbox_url)
        if ts is not None:
            toolsets.append(ts)

    # 2. Check Google-Managed Remote BigQuery MCP (`MCP_SERVER_URL` or `ENABLE_MANAGED_BQ_MCP=true`)
    managed_url = os.environ.get("MCP_SERVER_URL", "").strip()
    enable_managed = os.environ.get("ENABLE_MANAGED_BQ_MCP", "false").strip().lower() in ("1", "true", "yes")
    if managed_url or enable_managed:
        target_url = managed_url or MANAGED_BQ_MCP_URL
        ts = _build_managed_bigquery_mcp_toolset(target_url)
        if ts is not None:
            toolsets.append(ts)

    return toolsets


def get_mcp_architecture_info() -> dict[str, Any]:
    """Return metadata describing the BigQuery MCP configuration for diagnostics & demos."""
    return {
        "project_id": os.environ.get("GOOGLE_CLOUD_PROJECT", PROJECT_ID),
        "dataset": os.environ.get("BIGQUERY_DATASET", DATASET),
        "managed_bigquery_mcp_endpoint": MANAGED_BQ_MCP_URL,
        "tools_yaml_path": str(TOOLS_YAML_PATH),
        "tools_yaml_exists": TOOLS_YAML_PATH.exists(),
        "active_mcp_toolbox_url": os.environ.get("MCP_TOOLBOX_URL", ""),
        "enable_managed_bq_mcp": os.environ.get("ENABLE_MANAGED_BQ_MCP", "false"),
    }
