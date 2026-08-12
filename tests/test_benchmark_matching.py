import unittest

from dosweb.benchmark.matching import match_case, match_cases, normalize_route


def candidate(identifier="candidate:1", verdict="static_vulnerable", route="POST /api/v1/{id}"):
    return {
        "candidate_id": identifier,
        "repository": "owner/repo",
        "verdict": verdict,
        "finding": {"finding_id": "F-1"},
        "entry": {"route_or_event": route, "registration": {}},
        "route_or_event": route,
        "protocol": "http",
        "handler": {"callable": "ExampleController.create"},
        "resource_point": {"dimension": "bytes", "receiver": "body"},
    }


class BenchmarkMatchingTests(unittest.TestCase):
    def test_route_normalization_preserves_case(self):
        self.assertEqual(normalize_route("POST /api/v1/{deviceToken}/?x=1"), "/api/v1/{}")
        self.assertEqual(normalize_route("/API//v1/{id}"), "/API/v1/{}")

    def test_exact_finding_and_route_verdict_mapping(self):
        truth = {
            "case_id": "c",
            "repository": "owner/repo",
            "finding_id": "F-1",
            "truth_id": "truth:c",
            "title": "request body",
            "entry": "POST /api/v1/{deviceToken}",
        }
        self.assertEqual(match_case(truth, [candidate()])["status"], "hit")
        self.assertEqual(
            match_case(truth, [candidate(verdict="static_unknown")])["status"],
            "matched_static_unknown",
        )
        self.assertEqual(
            match_case(
                truth,
                [candidate(verdict="bounded_under_modeled_assumptions")],
            )["status"],
            "matched_bounded",
        )

    def test_grpc_truth_rejects_http_tcp_and_missing_protocol_candidates(self):
        truth = {
            "case_id": "grpc",
            "repository": "owner/repo",
            "finding_id": "F-1",
            "entry": "gRPC /fixture.Service/Upload",
        }
        http = candidate(route="/fixture.Service/Upload")
        tcp = {**http, "candidate_id": "candidate:tcp", "protocol": "tcp"}
        missing = {**http, "candidate_id": "candidate:missing", "protocol": ""}
        self.assertEqual(match_case(truth, [http])["status"], "no_candidate")
        self.assertEqual(match_case(truth, [tcp])["status"], "no_candidate")
        self.assertEqual(match_case(truth, [missing])["status"], "no_candidate")

    def test_finding_id_does_not_override_conflicting_route(self):
        truth = {
            "case_id": "route-conflict",
            "repository": "owner/repo",
            "finding_id": "F-1",
            "entry": "POST /expected",
        }
        self.assertEqual(
            match_case(truth, [candidate(route="POST /different")])["status"],
            "no_candidate",
        )

    def test_http_method_is_only_parsed_from_route_prefix(self):
        truth = {
            "case_id": "method",
            "repository": "owner/repo",
            "entry": "POST /api/get/items",
        }
        self.assertEqual(
            match_case(truth, [candidate(route="POST /api/get/items")])["status"],
            "hit",
        )

    def test_trace_and_connect_method_conflicts_fail_closed(self):
        trace = {
            "case_id": "trace",
            "repository": "owner/repo",
            "entry": "TRACE /api/items",
        }
        connect = {**trace, "case_id": "connect", "entry": "CONNECT /api/items"}
        post = candidate(route="POST /api/items")
        self.assertEqual(match_case(trace, [post])["status"], "no_candidate")
        self.assertEqual(match_case(connect, [post])["status"], "no_candidate")

    def test_title_and_handler_tokens_do_not_create_a_match(self):
        truth = {
            "case_id": "heuristic",
            "repository": "owner/repo",
            "title": "request body queue exhaustion",
            "entry": "",
        }
        self.assertEqual(match_case(truth, [candidate()])["status"], "no_candidate")

    def test_ambiguity_invalid_verdict_and_fail_closed_states(self):
        truth = {
            "case_id": "c",
            "repository": "owner/repo",
            "finding_id": "F-1",
            "entry": "POST /api/v1/{id}",
        }
        self.assertEqual(
            match_case(truth, [candidate(), candidate("candidate:2")])["status"],
            "ambiguous",
        )
        self.assertEqual(
            match_case(truth, [candidate(verdict="confirmed")])["status"],
            "truth_invalid",
        )
        self.assertEqual(
            match_case(truth, [], error="target_not_run")["status"],
            "target_not_run",
        )
        self.assertEqual(match_cases([truth], {})[0]["status"], "target_not_run")
