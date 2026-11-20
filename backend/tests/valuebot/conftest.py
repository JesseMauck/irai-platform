import dataclasses

import pytest

import valuebot.config as config


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """Offline settings with an isolated runs directory."""
    s = dataclasses.replace(config.settings, offline=True, anthropic_api_key="", data_dir=tmp_path / "runs")
    for mod in ("valuebot.config", "valuebot.pipeline", "valuebot.analysis", "valuebot.data.provider",
                "valuebot.llm.agent"):
        monkeypatch.setattr(f"{mod}.settings", s, raising=False)
    return s
