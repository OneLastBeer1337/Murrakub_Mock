"""
Registry and Eligibility Resolver — §4.2's untested claim, now tested.

Outside PoC scope. Owner: 083 / 035.
"""
import pytest

from poc.formulation.types import ProfileSpec, Task, TaskId
from prototype.registry import (ExecutorRegistry, UnknownTaskType, resolve, unservable)


def profile(pid, ptype, rel, lat):
    return ProfileSpec(pid, ptype, throughput=10.0, gpus=1, price=100.0,
                       reliability=rel, latency=lat)


def task(name, ttype, rel_floor=0.0, lat_ceil=1e9):
    return Task(TaskId("wf", name), ttype, load=5.0,
                rel_floor=rel_floor, lat_ceil=lat_ceil)


@pytest.fixture
def registry():
    r = ExecutorRegistry()
    r.register(profile("fast", "parse", rel=0.97, lat=40))
    r.register(profile("thorough", "parse", rel=0.995, lat=90))
    r.register(profile("small", "classify", rel=0.94, lat=60))
    return r


def test_exact_match_only(registry):
    """No fuzzy or semantic matching (§4.2). 'parsing' is not 'parse'."""
    with pytest.raises(UnknownTaskType):
        registry.profiles_for("parsing")


def test_registry_gap_raises_rather_than_returning_empty(registry):
    """§4.2's central claim: gaps surface as failures, not silent quality loss.

    An unknown type and a fully-filtered pool are different bugs needing different fixes,
    so they must not both present as an empty pool.
    """
    with pytest.raises(UnknownTaskType, match="summarise"):
        resolve([task("t1", "summarise")], registry)


def test_floors_filter_within_a_matched_type(registry):
    pools = resolve([task("t1", "parse", rel_floor=0.99)], registry)
    assert pools[TaskId("wf", "t1")] == ["thorough"]


def test_latency_ceiling_filters(registry):
    pools = resolve([task("t1", "parse", lat_ceil=50)], registry)
    assert pools[TaskId("wf", "t1")] == ["fast"]


def test_registered_type_with_everything_filtered_returns_empty_pool(registry):
    """Distinct from a registry gap: this is a floors problem and returns [] for the
    Optimizer to report as Infeasible(C1) naming the task (§4.1)."""
    tasks = [task("t1", "parse", rel_floor=0.999)]
    pools = resolve(tasks, registry)
    assert pools[TaskId("wf", "t1")] == []
    assert unservable(pools) == [TaskId("wf", "t1")]


def test_pools_are_deterministic(registry):
    tasks = [task("t1", "parse")]
    assert resolve(tasks, registry) == resolve(tasks, registry)
    assert resolve(tasks, registry)[TaskId("wf", "t1")] == ["fast", "thorough"]
