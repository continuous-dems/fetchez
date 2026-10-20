import pytest

import fetchez.api as api


# @pytest.mark.xfail(strict=True, reason="get() returns [] for module discovery exceptions irrespective of ignore_failures")
def test_api_get_discovery_error_propagates_in_strict_mode(monkeypatch):
    class BrokenModule:
        name = "broken"
        results = []

        def __init__(self, **kwargs):
            pass

        def run(self):
            raise RuntimeError("discovery unavailable")

    monkeypatch.setattr(api.ModuleRegistry, "load_all", lambda: None)
    monkeypatch.setattr(api.HookRegistry, "load_all", lambda: None)
    monkeypatch.setattr(api.ModuleRegistry, "get_class", lambda name: BrokenModule)
    with pytest.raises(RuntimeError, match="discovery unavailable"):
        api.get("broken", ignore_failures=False)
