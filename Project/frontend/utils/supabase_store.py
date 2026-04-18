from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd
import requests

try:
    import streamlit as st
except Exception:  # pragma: no cover - streamlit is only available in app runtime
    st = None

_SUPABASE_URL: Optional[str] = None
_SUPABASE_KEY: Optional[str] = None


def _get_config_value(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value:
        return value

    if st is not None:
        try:
            if hasattr(st, "secrets") and name in st.secrets:
                secret_value = st.secrets.get(name)
                if secret_value:
                    return secret_value
        except Exception:
            pass

    return default


def get_default_user_id() -> str:
    return _get_config_value("DEFAULT_USER_ID", "00000000-0000-0000-0000-000000000001")


def _get_supabase_config() -> tuple[str, str]:
    global _SUPABASE_URL, _SUPABASE_KEY

    if _SUPABASE_URL and _SUPABASE_KEY:
        return _SUPABASE_URL, _SUPABASE_KEY

    supabase_url = _get_config_value("SUPABASE_URL")
    supabase_key = _get_config_value("SUPABASE_SERVICE_ROLE_KEY") or _get_config_value("SUPABASE_ANON_KEY")

    if not supabase_url or not supabase_key:
        raise RuntimeError(
            "Supabase connection is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY)."
        )

    _SUPABASE_URL = supabase_url.rstrip("/")
    _SUPABASE_KEY = supabase_key
    return _SUPABASE_URL, _SUPABASE_KEY


def _get_supabase_headers() -> Dict[str, str]:
    _, supabase_key = _get_supabase_config()
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _supabase_request(method: str, path: str, params: Optional[Dict[str, str]] = None, json_body: Any = None) -> Any:
    supabase_url, _ = _get_supabase_config()
    response = requests.request(
        method=method,
        url=f"{supabase_url}{path}",
        headers=_get_supabase_headers(),
        params=params,
        json=json_body,
        timeout=30,
    )

    if response.status_code >= 400:
        error_text = response.text
        if "row-level security" in error_text.lower() or "42501" in error_text:
            error_text += (
                " | RLS blocked this request. Use SUPABASE_SERVICE_ROLE_KEY for local testing, "
                "or add SELECT/INSERT/UPDATE policies for the anonymous role on analysis_runs and analyzed_reviews."
            )
        raise RuntimeError(f"Supabase API error {response.status_code}: {error_text}")

    if not response.text.strip():
        return []

    try:
        return response.json()
    except ValueError:
        return []


def _rest_eq(value: Any) -> str:
    if isinstance(value, bool):
        value = str(value).lower()
    return f"eq.{value}"


def _load_all_reviews_by_run_id(run_id: str, page_size: int = 1000) -> List[Dict[str, Any]]:
    all_rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        page = _supabase_request(
            "GET",
            "/rest/v1/analyzed_reviews",
            params={
                "select": "*",
                "run_id": _rest_eq(run_id),
                "order": "id.asc",
                "limit": str(page_size),
                "offset": str(offset),
            },
        )

        if not page:
            break

        all_rows.extend(page)

        if len(page) < page_size:
            break

        offset += page_size

    return all_rows


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime().astimezone(timezone.utc).isoformat()

    if isinstance(value, (datetime,)):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass

    if isinstance(value, (list, dict, str, int, float, bool)):
        return value

    return value


def _chunk_records(records: List[Dict[str, Any]], chunk_size: int = 500) -> Iterable[List[Dict[str, Any]]]:
    for index in range(0, len(records), chunk_size):
        yield records[index:index + chunk_size]


def save_processed_data_to_supabase(processed_df: pd.DataFrame, source_filename: str, user_id: str) -> str:
    if processed_df is None:
        raise ValueError("processed_df cannot be None")

    source_filename = source_filename or "uploaded_data"
    row_count = int(len(processed_df))

    new_run_payload = {
        "user_id": user_id,
        "source_filename": source_filename,
        "row_count": row_count,
        "status": "processing",
        "is_current": False,
        "metadata": {
            "source": "streamlit_upload",
            "columns": list(processed_df.columns),
        },
    }

    new_run_response = _supabase_request(
        "POST",
        "/rest/v1/analysis_runs",
        params={"select": "id"},
        json_body=new_run_payload,
    )
    if not new_run_response:
        raise RuntimeError("Failed to create analysis run")

    run_id = new_run_response[0]["id"]

    records = processed_df.to_dict(orient="records")
    normalized_records: List[Dict[str, Any]] = []
    for row in records:
        cleaned_row: Dict[str, Any] = {}
        for key, value in row.items():
            cleaned_row[key] = _normalize_value(value)
        cleaned_row["run_id"] = run_id
        cleaned_row["user_id"] = user_id
        normalized_records.append(cleaned_row)

    if normalized_records:
        for batch in _chunk_records(normalized_records):
            _supabase_request("POST", "/rest/v1/analyzed_reviews", json_body=batch)

    current_runs_response = _supabase_request(
        "GET",
        "/rest/v1/analysis_runs",
        params={
            "select": "id",
            "user_id": _rest_eq(user_id),
            "is_current": _rest_eq(True),
        },
    )
    current_run_ids = [row["id"] for row in (current_runs_response or []) if row.get("id") != run_id]

    if current_run_ids:
        for current_run_id in current_run_ids:
            _supabase_request(
                "PATCH",
                "/rest/v1/analysis_runs",
                params={"id": _rest_eq(current_run_id)},
                json_body={"is_current": False},
            )

    _supabase_request(
        "PATCH",
        "/rest/v1/analysis_runs",
        params={"id": _rest_eq(run_id)},
        json_body={
            "status": "completed",
            "is_current": True,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    return run_id


def load_current_data_from_supabase(user_id: str) -> Optional[pd.DataFrame]:
    current_run_response = _supabase_request(
        "GET",
        "/rest/v1/analysis_runs",
        params={
            "select": "id,source_filename,row_count,status,is_current,metadata,created_at,completed_at",
            "user_id": _rest_eq(user_id),
            "is_current": _rest_eq(True),
            "order": "created_at.desc",
            "limit": "1",
        },
    )

    if not current_run_response:
        return None

    run_id = current_run_response[0]["id"]

    reviews_response = _load_all_reviews_by_run_id(run_id)

    if not reviews_response:
        return None

    reviews_df = pd.DataFrame(reviews_response)

    for column in reviews_df.columns:
        if reviews_df[column].dtype == "object":
            reviews_df[column] = reviews_df[column].where(reviews_df[column].notna(), None)

    return reviews_df


def list_analysis_runs_from_supabase(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    limit_value = max(1, min(int(limit), 500))
    runs_response = _supabase_request(
        "GET",
        "/rest/v1/analysis_runs",
        params={
            "select": "id,source_filename,row_count,status,is_current,created_at,completed_at,metadata",
            "user_id": _rest_eq(user_id),
            "order": "created_at.desc",
            "limit": str(limit_value),
        },
    )

    return runs_response or []


def list_reset_history_runs_from_supabase(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    runs = list_analysis_runs_from_supabase(user_id, limit=limit)
    filtered_runs: List[Dict[str, Any]] = []
    for run in runs:
        metadata = run.get("metadata")
        if isinstance(metadata, dict) and metadata.get("history_reason") == "reset":
            filtered_runs.append(run)
    return filtered_runs


def archive_current_run_on_reset(user_id: str) -> Optional[str]:
    current_run_response = _supabase_request(
        "GET",
        "/rest/v1/analysis_runs",
        params={
            "select": "id,metadata",
            "user_id": _rest_eq(user_id),
            "is_current": _rest_eq(True),
            "order": "created_at.desc",
            "limit": "1",
        },
    )

    if not current_run_response:
        return None

    current_run = current_run_response[0]
    run_id = current_run.get("id")
    if not run_id:
        return None

    metadata = current_run.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    metadata["history_reason"] = "reset"
    metadata["archived_at"] = datetime.now(timezone.utc).isoformat()

    _supabase_request(
        "PATCH",
        "/rest/v1/analysis_runs",
        params={"id": _rest_eq(run_id)},
        json_body={
            "is_current": False,
            "metadata": metadata,
        },
    )

    return run_id


def load_run_data_from_supabase(run_id: str) -> Optional[pd.DataFrame]:
    if not run_id:
        return None

    reviews_response = _load_all_reviews_by_run_id(run_id)

    if not reviews_response:
        return None

    reviews_df = pd.DataFrame(reviews_response)

    for column in reviews_df.columns:
        if reviews_df[column].dtype == "object":
            reviews_df[column] = reviews_df[column].where(reviews_df[column].notna(), None)

    return reviews_df


def clear_reset_history_runs_from_supabase(user_id: str, limit: int = 1000) -> int:
    history_runs = list_reset_history_runs_from_supabase(user_id, limit=limit)
    if not history_runs:
        return 0

    deleted_count = 0
    for run in history_runs:
        run_id = run.get("id")
        if not run_id:
            continue

        _supabase_request(
            "DELETE",
            "/rest/v1/analyzed_reviews",
            params={"run_id": _rest_eq(run_id)},
        )

        _supabase_request(
            "DELETE",
            "/rest/v1/analysis_runs",
            params={
                "id": _rest_eq(run_id),
                "user_id": _rest_eq(user_id),
            },
        )
        deleted_count += 1

    return deleted_count