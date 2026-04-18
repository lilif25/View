from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

_SCHEMA_READY = False


def _get_config_value(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value:
        return value

    if st is not None:
        try:
            if hasattr(st, "secrets") and name in st.secrets:
                secret_value = st.secrets.get(name)
                if secret_value:
                    return str(secret_value)
        except Exception:
            pass

    return default


def get_default_user_id() -> str:
    return _get_config_value("DEFAULT_USER_ID", "00000000-0000-0000-0000-000000000001")


def _get_offline_db_path() -> Path:
    configured = _get_config_value("OFFLINE_DB_PATH")
    if configured:
        db_path = Path(configured).expanduser()
        if not db_path.is_absolute():
            base = Path(__file__).resolve().parents[1]
            db_path = (base / db_path).resolve()
        return db_path

    return (Path(__file__).resolve().parents[1] / "offline_demo.db").resolve()


def _get_schema_path() -> Path:
    return (Path(__file__).resolve().parents[1] / "offline_schema.sql").resolve()


def _ensure_schema() -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY:
        return

    schema_path = _get_schema_path()
    if not schema_path.exists():
        raise RuntimeError(f"offline_schema.sql not found: {schema_path}")

    db_path = _get_offline_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(schema_path.read_text(encoding="utf-8"))
        conn.commit()
        _SCHEMA_READY = True
    finally:
        conn.close()


def _get_conn() -> sqlite3.Connection:
    _ensure_schema()
    conn = sqlite3.connect(str(_get_offline_db_path()))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _json_dumps(value: Any) -> str:
    if value is None:
        return "{}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _json_loads(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_value(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.to_pydatetime().astimezone(timezone.utc).isoformat()

    if isinstance(value, datetime):
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

    return value


def _ensure_local_user(conn: sqlite3.Connection, user_id: str) -> None:
    existing = conn.execute(
        "SELECT local_user_id FROM offline_app_users WHERE local_user_id = ?",
        (user_id,),
    ).fetchone()
    if existing:
        return

    now = _utc_now_iso()
    conn.execute(
        """
        INSERT INTO offline_app_users (
            local_user_id,
            cloud_user_id,
            created_at,
            updated_at,
            sync_status
        ) VALUES (?, ?, ?, ?, 'pending')
        """,
        (user_id, user_id, now, now),
    )


def _compute_review_hash(row: Dict[str, Any]) -> Optional[str]:
    base = "|".join(
        [
            str(row.get("product_id") or ""),
            str(row.get("product_name") or ""),
            str(row.get("rating") or ""),
            str(row.get("review_content") or ""),
            str(row.get("review_date") or ""),
        ]
    )
    if not base.replace("|", ""):
        return None
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def save_processed_data_to_offline(processed_df: pd.DataFrame, source_filename: str, user_id: str) -> str:
    if processed_df is None:
        raise ValueError("processed_df cannot be None")

    source_filename = source_filename or "uploaded_data"
    run_id = str(uuid.uuid4())
    now = _utc_now_iso()

    metadata = {
        "source": "streamlit_upload_offline",
        "columns": list(processed_df.columns),
    }

    conn = _get_conn()
    try:
        _ensure_local_user(conn, user_id)

        conn.execute(
            """
            UPDATE offline_analysis_runs
            SET is_current = 0, updated_at = ?
            WHERE local_user_id = ? AND is_current = 1
            """,
            (now, user_id),
        )

        conn.execute(
            """
            INSERT INTO offline_analysis_runs (
                local_run_id,
                local_user_id,
                cloud_user_id,
                source_filename,
                row_count,
                status,
                is_current,
                metadata,
                created_at,
                updated_at,
                sync_status
            ) VALUES (?, ?, ?, ?, ?, 'processing', 0, ?, ?, ?, 'pending')
            """,
            (
                run_id,
                user_id,
                user_id,
                source_filename,
                int(len(processed_df)),
                _json_dumps(metadata),
                now,
                now,
            ),
        )

        records = processed_df.to_dict(orient="records")
        for record in records:
            normalized = {k: _normalize_value(v) for k, v in record.items()}
            review_hash = normalized.get("review_hash") or _compute_review_hash(normalized)
            conn.execute(
                """
                INSERT OR REPLACE INTO offline_analyzed_reviews (
                    local_review_id,
                    local_run_id,
                    cloud_run_id,
                    local_user_id,
                    cloud_user_id,
                    product_id,
                    product_name,
                    rating,
                    review_content,
                    sentiment_score,
                    product_category,
                    sentiment_label,
                    solution,
                    review_date,
                    review_hash,
                    created_at,
                    updated_at,
                    sync_status
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
                """,
                (
                    str(uuid.uuid4()),
                    run_id,
                    user_id,
                    user_id,
                    normalized.get("product_id"),
                    normalized.get("product_name"),
                    normalized.get("rating"),
                    normalized.get("review_content"),
                    normalized.get("sentiment_score"),
                    normalized.get("product_category"),
                    normalized.get("sentiment_label"),
                    normalized.get("solution"),
                    normalized.get("review_date"),
                    review_hash,
                    now,
                    now,
                ),
            )

        conn.execute(
            """
            UPDATE offline_analysis_runs
            SET status = 'completed',
                is_current = 1,
                completed_at = ?,
                updated_at = ?
            WHERE local_run_id = ?
            """,
            (now, now, run_id),
        )

        conn.commit()
        return run_id
    finally:
        conn.close()


def _rows_to_df(rows: List[sqlite3.Row]) -> Optional[pd.DataFrame]:
    if not rows:
        return None

    data = [dict(row) for row in rows]
    df = pd.DataFrame(data)

    for column in df.columns:
        if df[column].dtype == "object":
            df[column] = df[column].where(df[column].notna(), None)

    return df


def load_run_data_from_offline(run_id: str) -> Optional[pd.DataFrame]:
    if not run_id:
        return None

    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM offline_analyzed_reviews
            WHERE local_run_id = ?
            ORDER BY created_at ASC
            """,
            (run_id,),
        ).fetchall()
        return _rows_to_df(rows)
    finally:
        conn.close()


def load_current_data_from_offline(user_id: str) -> Optional[pd.DataFrame]:
    conn = _get_conn()
    try:
        row = conn.execute(
            """
            SELECT local_run_id
            FROM offline_analysis_runs
            WHERE local_user_id = ? AND is_current = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        if not row:
            return None

        run_id = row["local_run_id"]
    finally:
        conn.close()

    return load_run_data_from_offline(run_id)


def list_reset_history_runs_from_offline(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    limit_value = max(1, min(int(limit), 500))
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                local_run_id AS id,
                source_filename,
                row_count,
                status,
                is_current,
                created_at,
                completed_at,
                metadata,
                history_reason,
                archived_at
            FROM offline_analysis_runs
            WHERE local_user_id = ?
              AND history_reason = 'reset'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit_value),
        ).fetchall()

        result: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["is_current"] = bool(item.get("is_current"))
            item["metadata"] = _json_loads(item.get("metadata"))
            result.append(item)

        return result
    finally:
        conn.close()


def archive_current_run_on_reset_offline(user_id: str) -> Optional[str]:
    now = _utc_now_iso()
    conn = _get_conn()
    try:
        row = conn.execute(
            """
            SELECT local_run_id, metadata
            FROM offline_analysis_runs
            WHERE local_user_id = ? AND is_current = 1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()

        if not row:
            return None

        run_id = row["local_run_id"]
        metadata = _json_loads(row["metadata"])
        metadata["history_reason"] = "reset"
        metadata["archived_at"] = now

        conn.execute(
            """
            UPDATE offline_analysis_runs
            SET is_current = 0,
                history_reason = 'reset',
                archived_at = ?,
                metadata = ?,
                updated_at = ?,
                sync_status = 'pending'
            WHERE local_run_id = ?
            """,
            (now, _json_dumps(metadata), now, run_id),
        )
        conn.commit()
        return run_id
    finally:
        conn.close()


def clear_reset_history_runs_from_offline(user_id: str, limit: int = 1000) -> int:
    limit_value = max(1, min(int(limit), 5000))
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT local_run_id
            FROM offline_analysis_runs
            WHERE local_user_id = ?
              AND history_reason = 'reset'
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit_value),
        ).fetchall()

        run_ids = [row["local_run_id"] for row in rows]
        if not run_ids:
            return 0

        for run_id in run_ids:
            conn.execute(
                "DELETE FROM offline_analyzed_reviews WHERE local_run_id = ?",
                (run_id,),
            )
            conn.execute(
                "DELETE FROM offline_analysis_runs WHERE local_run_id = ?",
                (run_id,),
            )

        conn.commit()
        return len(run_ids)
    finally:
        conn.close()
