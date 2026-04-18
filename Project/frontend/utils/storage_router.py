from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pandas as pd

from utils.offline_store import (
    archive_current_run_on_reset_offline,
    clear_reset_history_runs_from_offline,
    get_default_user_id as get_default_user_id_offline,
    list_reset_history_runs_from_offline,
    load_current_data_from_offline,
    load_run_data_from_offline,
    save_processed_data_to_offline,
)
from utils.supabase_store import (
    archive_current_run_on_reset,
    clear_reset_history_runs_from_supabase,
    get_default_user_id as get_default_user_id_supabase,
    list_reset_history_runs_from_supabase,
    load_current_data_from_supabase,
    load_run_data_from_supabase,
    save_processed_data_to_supabase,
)

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

_LAST_EFFECTIVE_MODE = "online"


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


def get_storage_mode() -> str:
    mode = (_get_config_value("STORAGE_MODE", "hybrid") or "hybrid").strip().lower()
    if mode not in {"online", "offline", "hybrid"}:
        return "hybrid"
    return mode


def _set_effective_mode(mode: str) -> None:
    global _LAST_EFFECTIVE_MODE
    _LAST_EFFECTIVE_MODE = mode


def get_effective_storage_mode() -> str:
    return _LAST_EFFECTIVE_MODE


def get_default_user_id() -> str:
    user_id = get_default_user_id_supabase()
    if user_id:
        return user_id
    return get_default_user_id_offline()


def save_processed_data(processed_df: pd.DataFrame, source_filename: str, user_id: str) -> str:
    mode = get_storage_mode()

    if mode == "offline":
        _set_effective_mode("offline")
        return save_processed_data_to_offline(processed_df, source_filename, user_id)

    if mode == "online":
        _set_effective_mode("online")
        return save_processed_data_to_supabase(processed_df, source_filename, user_id)

    try:
        result = save_processed_data_to_supabase(processed_df, source_filename, user_id)
        _set_effective_mode("online")
        return result
    except Exception:
        _set_effective_mode("offline")
        return save_processed_data_to_offline(processed_df, source_filename, user_id)


def load_current_data(user_id: str) -> Optional[pd.DataFrame]:
    mode = get_storage_mode()

    if mode == "offline":
        _set_effective_mode("offline")
        return load_current_data_from_offline(user_id)

    if mode == "online":
        _set_effective_mode("online")
        return load_current_data_from_supabase(user_id)

    try:
        result = load_current_data_from_supabase(user_id)
        _set_effective_mode("online")
        return result
    except Exception:
        _set_effective_mode("offline")
        return load_current_data_from_offline(user_id)


def list_reset_history_runs(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    mode = get_storage_mode()

    if mode == "offline":
        _set_effective_mode("offline")
        return list_reset_history_runs_from_offline(user_id, limit=limit)

    if mode == "online":
        _set_effective_mode("online")
        return list_reset_history_runs_from_supabase(user_id, limit=limit)

    try:
        result = list_reset_history_runs_from_supabase(user_id, limit=limit)
        _set_effective_mode("online")
        return result
    except Exception:
        _set_effective_mode("offline")
        return list_reset_history_runs_from_offline(user_id, limit=limit)


def load_run_data(run_id: str) -> Optional[pd.DataFrame]:
    mode = get_storage_mode()

    if mode == "offline":
        _set_effective_mode("offline")
        return load_run_data_from_offline(run_id)

    if mode == "online":
        _set_effective_mode("online")
        return load_run_data_from_supabase(run_id)

    try:
        result = load_run_data_from_supabase(run_id)
        _set_effective_mode("online")
        return result
    except Exception:
        _set_effective_mode("offline")
        return load_run_data_from_offline(run_id)


def archive_current_run_on_reset_data(user_id: str) -> Optional[str]:
    mode = get_storage_mode()

    if mode == "offline":
        _set_effective_mode("offline")
        return archive_current_run_on_reset_offline(user_id)

    if mode == "online":
        _set_effective_mode("online")
        return archive_current_run_on_reset(user_id)

    try:
        result = archive_current_run_on_reset(user_id)
        _set_effective_mode("online")
        return result
    except Exception:
        _set_effective_mode("offline")
        return archive_current_run_on_reset_offline(user_id)


def clear_reset_history_runs_data(user_id: str, limit: int = 1000) -> int:
    mode = get_storage_mode()

    if mode == "offline":
        _set_effective_mode("offline")
        return clear_reset_history_runs_from_offline(user_id, limit=limit)

    if mode == "online":
        _set_effective_mode("online")
        return clear_reset_history_runs_from_supabase(user_id, limit=limit)

    try:
        result = clear_reset_history_runs_from_supabase(user_id, limit=limit)
        _set_effective_mode("online")
        return result
    except Exception:
        _set_effective_mode("offline")
        return clear_reset_history_runs_from_offline(user_id, limit=limit)
