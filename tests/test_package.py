from __future__ import annotations

# Copyright (c) 2026 Jamie Nelson


def test_package_imports() -> None:
    import agent_marketplace_versioner

    assert agent_marketplace_versioner.__name__ == "agent_marketplace_versioner"
