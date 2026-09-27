from __future__ import annotations

import pytest

from dosweb.configuration.models import ModeledConfigurationFact
from dosweb.production import _configuration_relevant_to_growth_dimension


def _fact(
    key: str,
    *,
    value: int | None = 1024,
    default_effective: bool = True,
    status: str = "known",
) -> ModeledConfigurationFact:
    return ModeledConfigurationFact(
        key,
        value,
        "application.yml",
        1,
        "default",
        "config_file",
        default_effective,
        status,
    )


@pytest.mark.parametrize(
    "key",
    (
        "server.max-http-request-size",
        "spring.servlet.multipart.max-request-size",
        "quarkus.http.limits.max-body-size",
        "server.tomcat.max-http-form-post-size",
        "request.payload.limit",
    ),
)
def test_body_byte_limits_are_growth_slice_relevant(key: str) -> None:
    assert _configuration_relevant_to_growth_dimension(_fact(key), "bytes")


@pytest.mark.parametrize(
    "key",
    (
        "server.max-http-header-size",
        "server.max-request-header-size",
        "server.max-http-request-count",
        "security.requests-per-minute",
        "bucket4j.rate-limits.bandwidth.capacity",
        "gateway.ip.request-quota",
        "server.max-query-size",
        "server.max-uri-length",
    ),
)
def test_unrelated_channels_cannot_refute_body_byte_growth(key: str) -> None:
    assert not _configuration_relevant_to_growth_dimension(_fact(key), "bytes")


def test_unknown_configuration_is_never_slice_counterevidence() -> None:
    assert not _configuration_relevant_to_growth_dimension(
        _fact(
            "request.max-body-size",
            value=None,
            status="unknown",
            default_effective=False,
        ),
        "bytes",
    )


def test_queue_capacity_is_task_specific_not_body_specific() -> None:
    fact = _fact("executor.queue.capacity")
    assert _configuration_relevant_to_growth_dimension(fact, "tasks")
    assert not _configuration_relevant_to_growth_dimension(fact, "bytes")
