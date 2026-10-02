import os
import pytest
from aang.config.onboarding import run_doctor, save_env_config
from rich.console import Console

def test_save_env_config_local(tmp_path):
    target = tmp_path / ".env"
    save_env_config(
        {
            "AANG_PROVIDER": "groq",
            "AANG_MODEL": "openai/gpt-oss-120b",
            "GROQ_API_KEY": "gsk_test123"
        },
        save_global=False,
        target_path=str(target)
    )
    assert target.exists()
    content = target.read_text()
    assert "AANG_PROVIDER=groq" in content
    assert "AANG_MODEL=openai/gpt-oss-120b" in content
    assert "GROQ_API_KEY=gsk_test123" in content

def test_run_doctor():
    console = Console(record=True, force_terminal=False)
    run_doctor(console)
    output = console.export_text()
    assert "Aang System Diagnostics" in output
    assert "Python Version" in output
    assert "Git CLI" in output
