"""Configuration loader.

Layering: config/settings.yaml  <-  environment variables (.env / environment)  <-  code defaults.

Env var names are the flat keys in .env.example (LLM_PROVIDER, TODAY, ...).
Booleans/ints are coerced; unknown vars are ignored.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.llm.models import model_spec
from src.llm.providers import provider_defaults

ROOT = Path(__file__).resolve().parents[2]
CONFIG_FILE = ROOT / "config" / "settings.yaml"


def _as_type(value: str, hint: type):
    if hint is bool:
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if hint is int:
        return int(value)
    return value


@dataclass(frozen=True)
class Settings:
    provider: str = "mock"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.0
    max_tokens: int = 1024
    cost_per_1k_tokens: float = 0.0
    app_version: str = "1.0.0"

    db_path: str = "books.db"
    today: str = "2026-10-01"
    sql_timeout_seconds: int = 5
    sql_row_limit: int = 500
    agent_max_iterations: int = 6
    tenant_tables: tuple = ("accounts", "vouchers", "voucher_lines", "bills")
    forbidden_keywords: tuple = field(default_factory=lambda: (
        ("INSERT", "UPDATE", "DELETE", "REPLACE", "TRUNCATE", "MERGE"),
        ("DROP", "ALTER", "CREATE", "ATTACH", "DETACH", "PRAGMA", "VACUUM"),
        ("EXPLAIN", "REINDEX", "ANALYZE"),
    ))

    log_dir: str = "logs"
    tool_calls_file: str = "logs/tool_calls.jsonl"

    chat_history_size: int = 20
    default_user_id: str = "U301"
    seed_orgs: int = 3
    seed_months: int = 18
    seed_vouchers_per_month: int = 175
    seed_fixed_seed: int = 42

    def resolve(self, base: Path = ROOT) -> "Settings":
        """Materialize paths relative to repo root; keep the object frozen-safe."""
        return self

    @property
    def db_path_abs(self) -> Path:
        path = Path(self.db_path)
        return path if path.is_absolute() else ROOT / path

    @property
    def today_iso(self) -> str:
        from datetime import date

        return date.fromisoformat(self.today).isoformat()

    def org_id_for(self, user_id: str) -> str:
        from src.services.org_service import resolve_org

        return resolve_org(user_id)

    @property
    def tool_calls_file_abs(self) -> Path:
        path = Path(self.tool_calls_file)
        return path if path.is_absolute() else ROOT / path

    @property
    def log_dir_abs(self) -> Path:
        path = Path(self.log_dir)
        return path if path.is_absolute() else ROOT / path


def _env_overrides(yaml_cfg: dict) -> dict:
    """Map environment variables onto the same dotted-yaml keys."""
    mapping = {
        "LLM_PROVIDER": "llm.provider",
        "LLM_MODEL": "llm.model",
        "LLM_API_KEY": "llm.api_key",
        "LLM_BASE_URL": "llm.base_url",
        "TODAY": "guardrails.today",
        "DB_PATH": "db.path",
        "SQL_TIMEOUT_SECONDS": "guardrails.sql_timeout_seconds",
        "SQL_ROW_LIMIT": "guardrails.sql_row_limit",
        "AGENT_MAX_ITERATIONS": "guardrails.agent_max_iterations",
        "USER_ID": "services.default_user_id",
    }
    out = {}
    for env_key, dot_path in mapping.items():
        if env_key in os.environ and os.environ[env_key] != "":
            out[dot_path] = os.environ[env_key]
    return out


def _deep_set(config: dict, dot_path: str, value):
    """Set config[a][b][c] = value for the dotted key 'a.b.c', creating dicts as needed."""
    parts = dot_path.split(".")
    node = config
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def load_settings() -> Settings:
    yaml_config = {}
    if CONFIG_FILE.exists():
        yaml_config = yaml.safe_load(CONFIG_FILE.read_text(encoding="utf-8")) or {}
    for dot_path, value in _env_overrides(yaml_config).items():
        _deep_set(yaml_config, dot_path, value)

    guard_cfg = yaml_config.get("guardrails", {})
    llm_cfg = yaml_config.get("llm", {})
    db_cfg = yaml_config.get("db", {})
    log_cfg = yaml_config.get("logging", {})

    # the user only supplies provider + key (+ optional model); base_url,
    # default model and cost come from the provider table when not set
    provider = str(llm_cfg.get("provider", "mock")).lower()
    provider_table = provider_defaults(provider)
    model = str(llm_cfg.get("model") or provider_table.get("model", ""))
    base_url = str(llm_cfg.get("base_url") or provider_table.get("base_url") or "")
    cost_value = llm_cfg.get("cost_per_1k_tokens")
    cost_per_1k = (float(cost_value) if cost_value not in (None, "")
                   else float(provider_table.get("cost_per_1k", 0.0)))
    # model specs cap the per-call output budget: never ask for more than the
    # model can emit (the 1024 default stays unchanged, well under every cap)
    spec = model_spec(provider, model) or {}
    max_tokens = int(spec.get("max_output_tokens") or int(llm_cfg.get("max_tokens", 1024)))
    max_tokens = min(max_tokens, int(llm_cfg.get("max_tokens", 1024)))

    return Settings(
        provider=provider,
        model=model,
        api_key=str(llm_cfg.get("api_key", "") or os.environ.get("OPENAI_API_KEY", "")),
        base_url=base_url,
        temperature=float(llm_cfg.get("temperature", 0.0)),
        max_tokens=max_tokens,
        cost_per_1k_tokens=cost_per_1k,
        app_version=str(yaml_config.get("app", {}).get("version", "1.0.0")),
        db_path=str(db_cfg.get("path", "books.db")),
        today=str(guard_cfg.get("today", "2026-10-01")),
        sql_timeout_seconds=int(guard_cfg.get("sql_timeout_seconds", 5)),
        sql_row_limit=int(guard_cfg.get("sql_row_limit", 500)),
        agent_max_iterations=int(guard_cfg.get("agent_max_iterations", 6)),
        tenant_tables=tuple(guard_cfg.get("tenant_tables", ("accounts", "vouchers", "voucher_lines", "bills"))),
        forbidden_keywords=tuple(tuple(keywords) for keywords in guard_cfg.get("forbidden_keywords", ())),
        log_dir=str(log_cfg.get("dir", "logs")),
        tool_calls_file=str(log_cfg.get("tool_calls_file", "logs/tool_calls.jsonl")),
        default_user_id=str(yaml_config.get("services", {}).get("default_user_id", "U301")),
        seed_orgs=int(yaml_config.get("seed", {}).get("orgs", 3)),
        seed_months=int(yaml_config.get("seed", {}).get("months", 18)),
        seed_vouchers_per_month=int(yaml_config.get("seed", {}).get("vouchers_per_org_per_month", 175)),
        seed_fixed_seed=int(yaml_config.get("seed", {}).get("fixed_seed", 42)),
    )


SETTINGS = load_settings()