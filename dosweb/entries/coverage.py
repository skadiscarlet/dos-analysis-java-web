from __future__ import annotations

from typing import Final


_PATTERN_BINDINGS: Final = {
    ("spring_mvc", "annotation_mapping"): frozenset({
        "spring_annotation_mapping",
        "spring_spel_source_default_modeled_entry",
    }),
    ("spring_mvc", "static_registration"): frozenset({
        "armeria_annotated_service_registration",
    }),
    ("servlet", "annotation_mapping"): frozenset({
        "servlet_annotation_mapping",
        "spring_component_filter_default_registration",
    }),
    ("servlet", "static_registration"): frozenset({
        "filter_registration_bean",
        "jetty_servlet_holder_registration",
        "web_xml_servlet_mapping",
    }),
    ("netty", "pipeline_registration"): frozenset({
        "netty_pipeline_registration",
        "netty_source_switch_route_alias",
    }),
    ("mqtt", "subscription_registration"): frozenset({
        "mqtt_subscription_registration",
    }),
    ("mqtt", "broker_registration"): frozenset({
        "jmqtt_anonymous_channel_initializer",
        "jmqtt_object_callback_mqtt_conversion",
        "jmqtt_validate_message_process_protocol",
    }),
    ("jax_rs", "static_registration"): frozenset({
        "airlift_jaxrs_source_registration",
        "dropwizard_guice_source_registration",
        "jax_rs_static_registration",
        "sisu_named_guice_source_registration",
    }),
    ("grpc", "static_registration"): frozenset({
        "grpc_generated_client_or_bidi_streaming_registration",
        "grpc_generated_rpc_static_registration",
    }),
}


def registration_coverage_pattern_id(
    framework: str,
    registration_kind: str,
    supported_pattern: str,
) -> str | None:
    """Return an exact modeled identity; substring similarity has no meaning."""
    patterns = _PATTERN_BINDINGS.get((framework, registration_kind), frozenset())
    if supported_pattern not in patterns:
        return None
    return (
        "entry-registration-coverage:"
        f"{framework}:{registration_kind}:{supported_pattern}"
    )


def registration_coverage_pattern_ids(
    framework: str,
    registration_kind: str,
) -> tuple[str, ...]:
    """Return every exact modeled identity for one framework/kind pair."""
    return tuple(
        sorted(
            pattern_id
            for pattern in _PATTERN_BINDINGS.get(
                (framework, registration_kind), frozenset()
            )
            if (
                pattern_id := registration_coverage_pattern_id(
                    framework, registration_kind, pattern
                )
            )
            is not None
        )
    )


def registration_coverage_pattern_belongs_to_framework(
    framework: str,
    pattern_id: str,
) -> bool:
    """Reject fabricated or cross-framework supported coverage identities."""
    return any(
        pattern_id in registration_coverage_pattern_ids(framework, kind)
        for modeled_framework, kind in _PATTERN_BINDINGS
        if modeled_framework == framework
    )


__all__ = [
    "registration_coverage_pattern_belongs_to_framework",
    "registration_coverage_pattern_id",
    "registration_coverage_pattern_ids",
]
