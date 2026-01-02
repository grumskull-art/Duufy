import os
import sys
import types

from ai_parser_orchestrator import parse_input


def _set_env(values: dict[str, str | None]) -> dict[str, str | None]:
    previous: dict[str, str | None] = {}
    for key, value in values.items():
        previous[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    return previous


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_fallback_path() -> None:
    previous = _set_env({"DUUFY_AI_ENABLED": None})
    try:
        result = parse_input("milk, bread")
        assert result.source == "fallback"
        assert len(result.items) >= 2
    finally:
        _restore_env(previous)


def test_ai_disabled_path() -> None:
    previous = _set_env({"DUUFY_AI_ENABLED": "0"})
    try:
        result = parse_input("milk", force_ai=True)
        assert result.source == "fallback"
        assert "AI_DISABLED" in result.warnings
    finally:
        _restore_env(previous)


def test_ai_failed_path() -> None:
    previous = _set_env({"DUUFY_AI_ENABLED": "1"})
    module_name = "ai_provider_placeholder"
    original_module = sys.modules.get(module_name)
    try:
        placeholder = types.ModuleType(module_name)

        def parse(_: str) -> object:
            raise Exception("provider failure")

        placeholder.parse = parse
        sys.modules[module_name] = placeholder

        result = parse_input("milk", force_ai=True)
        assert result.source == "fallback"
        assert "AI_FAILED" in result.warnings
    finally:
        if original_module is None:
            sys.modules.pop(module_name, None)
        else:
            sys.modules[module_name] = original_module
        _restore_env(previous)


def main() -> None:
    test_fallback_path()
    test_ai_disabled_path()
    test_ai_failed_path()


if __name__ == "__main__":
    main()
