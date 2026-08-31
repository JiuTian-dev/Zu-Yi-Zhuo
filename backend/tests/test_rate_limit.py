import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.rate_limit import MutationRateLimiter
from app.api.repository import InMemoryTableRepository


def test_mutation_rate_limiter_is_sliding_and_key_scoped() -> None:
    now = [100.0]
    limiter = MutationRateLimiter(2, clock=lambda: now[0])

    assert limiter.allow("client-a") == (True, 0)
    assert limiter.allow("client-a") == (True, 0)
    allowed, retry_after = limiter.allow("client-a")
    assert allowed is False and 59 <= retry_after <= 60
    assert limiter.allow("client-b") == (True, 0)

    now[0] += 60.1
    assert limiter.allow("client-a") == (True, 0)


def test_rest_mutation_limit_returns_retry_after_without_limiting_reads() -> None:
    repository = InMemoryTableRepository()
    client = TestClient(create_app(repository, rest_max_mutations_per_minute=1))

    first = client.post("/tables", json={"table_id": "limited-1", "core_question": "Q"})
    second = client.post("/tables", json={"table_id": "limited-2", "core_question": "Q"})

    assert first.status_code == 201
    assert second.status_code == 429
    assert second.json() == {"detail": "too many REST mutations; retry later"}
    assert int(second.headers["retry-after"]) >= 1
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/tables/limited-1").status_code == 200


@pytest.mark.parametrize("value", [0, -1])
def test_rest_mutation_limit_must_be_positive(value: int) -> None:
    with pytest.raises(ValueError, match="rest_max_mutations_per_minute"):
        create_app(rest_max_mutations_per_minute=value)
