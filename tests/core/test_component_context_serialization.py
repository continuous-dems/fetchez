"""Regression tests for transient context on Fetchez modules and hooks.

The base classes exclude context from their serialized state; this does not
promise that arbitrary runtime components can be deep-copied or pickled.
"""

import copy
import pickle
import threading

import pytest

from fetchez.hooks.base import FetchHook
from fetchez.modules.base import FetchModule


class CopyableHook(FetchHook):
    """Top-level class so it is also suitable for pickle tests."""

    name = "copyable-test-hook"


class CopyableModule(FetchModule):
    """Top-level, minimally configured module without external resources."""

    name = "copyable-test-module"

    def run(self):
        return self


@pytest.fixture(params=[CopyableHook, CopyableModule], ids=["hook", "module"])
def component(request):
    cls = request.param
    obj = cls() if cls is CopyableHook else cls(use_cache=False)
    obj.instance_id = "source_a"
    obj.test_options = {"levels": [1, 2]}
    return obj


def active_context():
    """A context-shaped, deliberately noncopyable reference.

    A real FetchContext contains a threading.Event via its execution state;
    using an Event here isolates the base-class serialization contract.
    """
    return {"cancel_event": threading.Event()}


def test_getstate_excludes_context_without_mutating_original(component):
    context = active_context()
    component.context = context

    state = component.__getstate__()

    assert state["context"] is None
    assert state["instance_id"] == "source_a"
    assert state["test_options"] == {"levels": [1, 2]}
    assert component.context is context
    assert component.__dict__["context"] is context
    assert state is not component.__dict__


def test_deepcopy_drops_active_context_and_copies_other_state(component):
    context = active_context()
    component.context = context

    cloned = copy.deepcopy(component)

    assert cloned is not component
    assert cloned.context is None
    assert component.context is context
    assert cloned.instance_id == component.instance_id
    assert cloned.test_options == component.test_options
    assert cloned.test_options is not component.test_options
    cloned.test_options["levels"].append(3)
    assert component.test_options == {"levels": [1, 2]}


def test_pickle_roundtrip_drops_active_context_for_simple_components(component):
    context = active_context()
    component.context = context

    restored = pickle.loads(pickle.dumps(component))

    assert restored is not component
    assert restored.context is None
    assert restored.instance_id == component.instance_id
    assert restored.test_options == component.test_options
    assert component.context is context


def test_noncontext_runtime_resources_are_not_promised_serializable(component):
    """Excluding context must not hide unrelated, nonserializable resources."""
    component.context = active_context()
    component.test_resource = threading.Lock()

    state = component.__getstate__()
    assert state["context"] is None
    assert state["test_resource"] is component.test_resource

    with pytest.raises(TypeError, match="pickle|lock"):
        pickle.dumps(component)
    with pytest.raises(TypeError, match="pickle|lock"):
        copy.deepcopy(component)
