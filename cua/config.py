"""Configuration loader for CUA. Reads from config.yaml with env var fallback."""
import os
from pathlib import Path

import yaml


# Defaults
DEFAULTS = {
    "moonshot_api_key": "",
    "model": "kimi-k2.6",
    "base_url": "https://api.moonshot.cn/v1",
    "max_tokens": 32768,
    "max_iterations": 50,
    "jpeg_quality": 85,
    "overlay": {
        "circle_radius": 15,
        "outer_radius": 18,
        "line_width": 2,
        "outer_width": 4,
        "inner_width": 3,
        "color": "#e74c3c",
        "white": "#ffffff",
    },
    "learning": {
        "autoskill_enabled": True,          # Generate skills from successful tasks
        "autoskill_min_steps": 3,           # Minimum tool calls before learning
        "autoskill_max_skills": 50,         # Max stored skills before pruning
        "reflection_enabled": True,         # Analyze failures
        "reflection_max_prompt": 5,         # Past reflections to inject in prompt
        "learnings_max_prompt": 10,         # Past learnings to inject in prompt
        "pending_enabled": True,            # Save interrupted task traces
        "pending_max_retries": 3,           # Settlement retries before force-write
        "cleanup_days": 0,                  # Auto-delete learnings older than N days (0=never)
    },
}


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, return empty dict if not found."""
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    """Load configuration: defaults < config.yaml < environment variables."""
    config = DEFAULTS.copy()

    # Layer 1: config.yaml (next to this file, or in cwd)
    config_paths = [
        Path(__file__).parent / "config.yaml",
        Path("cua/config.yaml"),
    ]
    for path in config_paths:
        file_cfg = _load_yaml(path)
        if file_cfg:
            config = _deep_merge(config, file_cfg)
            break

    # Layer 2: Environment variable override
    if os.environ.get("MOONSHOT_API_KEY"):
        config["moonshot_api_key"] = os.environ["MOONSHOT_API_KEY"]

    return config
