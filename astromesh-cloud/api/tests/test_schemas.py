import pytest
from astromesh_cloud.schemas.agent import WizardConfig

def test_wizard_config_valid():
    config = WizardConfig(name="my-agent", display_name="My Agent", system_prompt="You are helpful.", model="ollama/llama3")
    assert config.name == "my-agent"
    assert config.tone == "professional"

def test_wizard_config_invalid_name():
    with pytest.raises(Exception):
        WizardConfig(name="My Agent!", display_name="My Agent", system_prompt="Test", model="ollama/llama3")
