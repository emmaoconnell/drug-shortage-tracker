"""
api.py — openFDA Drug Shortages API client.

The openFDA shortages endpoint returns up to 1000 records per request.
We paginate through all available records using the `skip` parameter.
No API key is required for low-volume usage (≤ 1000 req/day).
"""

import time
import requests
from typing import Optional

BASE_URL = "https://api.fda.gov/drug/shortages.json"
# Maximum records the API returns per call
PAGE_SIZE = 100
# Seconds to wait between paginated requests (be a polite API citizen)
REQUEST_DELAY = 0.3


def fetch_shortages(
    limit: int = 1000,
    search: Optional[str] = None,
) -> list[dict]:
    """
    Fetch drug shortage records from openFDA.

    Args:
        limit:  Total max records to retrieve (capped at 5000 for safety).
        search: Optional openFDA query string, e.g. 'status:"Resolved"'.

    Returns:
        List of raw result dicts from the API.
    """
    limit = min(limit, 5000)
    all_results: list[dict] = []
    skip = 0

    while len(all_results) < limit:
        batch_size = min(PAGE_SIZE, limit - len(all_results))
        params: dict = {"limit": batch_size, "skip": skip}
        if search:
            params["search"] = search

        try:
            resp = requests.get(BASE_URL, params=params, timeout=15)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as exc:
            # 404 means no results match the query — not a real error
            if exc.response is not None and exc.response.status_code == 404:
                break
            raise
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"openFDA request failed: {exc}") from exc

        data = resp.json()
        results = data.get("results", [])
        if not results:
            break

        all_results.extend(results)
        skip += len(results)

        # Stop early if we've reached the total available records
        total_available = data.get("meta", {}).get("results", {}).get("total", 0)
        if skip >= total_available:
            break

        time.sleep(REQUEST_DELAY)

    return all_results


def search_shortages(
    generic_name: str = "",
    brand_name: str = "",
    manufacturer: str = "",
    reason: str = "",
    limit: int = 500,
) -> list[dict]:
    """
    Build an openFDA search query from the provided field values and fetch.

    Fields are ANDed together; empty strings are ignored.
    Uses unquoted tokenized search (case-insensitive, partial-word safe) rather
    than exact phrase matching so that e.g. "amoxicillin" matches
    "Amoxicillin Trihydrate" in the openFDA index.
    """
    def _term(field: str, value: str) -> str:
        # Unquoted single token → tokenized (case-insensitive) match.
        # For multi-word input, wrap in quotes for phrase matching.
        v = value.strip().replace('"', "")
        return f'{field}:"{v}"' if " " in v else f"{field}:{v}"

    parts = []
    if generic_name:
        parts.append(_term("generic_name", generic_name))
    if brand_name:
        parts.append(_term("brand_name", brand_name))
    if manufacturer:
        # The shortages endpoint stores manufacturer as company_name,
        # not manufacturer_name (which lives under openfda.*).
        parts.append(_term("company_name", manufacturer))
    if reason:
        parts.append(_term("shortage_reason.reason_text", reason))

    query = " AND ".join(parts) if parts else None
    return fetch_shortages(limit=limit, search=query)


def get_api_stats() -> dict:
    """
    Return total record count and metadata from a lightweight API probe.
    Does not download full records — just peeks at the meta block.
    """
    try:
        resp = requests.get(BASE_URL, params={"limit": 1}, timeout=10)
        resp.raise_for_status()
        meta = resp.json().get("meta", {}).get("results", {})
        return {
            "total": meta.get("total", 0),
            "skip": meta.get("skip", 0),
            "limit": meta.get("limit", 0),
        }
    except Exception:
        return {"total": 0, "skip": 0, "limit": 0}
