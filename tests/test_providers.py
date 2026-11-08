from pydantic import SecretStr

from godot_forge.config import Settings
from godot_forge.models import OpenAIGodotModel, build_model


def test_deepseek_provider_has_compatible_defaults() -> None:
    settings = Settings(
        model_provider="deepseek",
        api_key=SecretStr("unit-test-key"),
    )

    assert settings.model_name == "deepseek-chat"
    assert settings.base_url == "https://api.deepseek.com/v1"
    assert settings.structured_output_method == "json_mode"
    assert isinstance(build_model(settings), OpenAIGodotModel)


def test_deepseek_settings_allow_custom_compatible_endpoint() -> None:
    settings = Settings(
        model_provider="deepseek",
        api_key=SecretStr("unit-test-key"),
        base_url="https://example.com/v1",
        structured_output_method="json_mode",
    )

    assert settings.base_url == "https://example.com/v1"
    assert settings.structured_output_method == "json_mode"
