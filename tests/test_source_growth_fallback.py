from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dosweb.entries import AttackerInputFact, EntryFact, HandlerFact, RegistrationFact
from dosweb.growth.source_fallback import source_backed_same_handler_growth


class SourceBackedGrowthFallbackTests(unittest.TestCase):
    def _entry(self, *, registration_callable: str) -> EntryFact:
        return EntryFact.create(
            framework="jax_rs",
            protocol="http",
            handler=HandlerFact(
                "example.StatementResource.postStatement",
                "module/src/main/java/example/StatementResource.java",
                8,
            ),
            registration=RegistrationFact(
                "static_registration",
                registration_callable,
                "module/src/main/java/example/CoordinatorModule.java",
                7,
            ),
            route_or_event="POST /v1/statement",
            auth_context="unknown",
            attacker_inputs=(AttackerInputFact("statement", "String", "request_body"),),
            materialization_phase="before_handler",
        )

    def test_airlift_same_handler_field_map_put_is_a_partial_source_supplement(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "module" / "src" / "main" / "java" / "example" / "StatementResource.java"
            source.parent.mkdir(parents=True)
            source.write_text(
                """package example;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
public class StatementResource {
  private final Map<String, Query> queries = new ConcurrentHashMap<>();

  @jakarta.ws.rs.POST
  public Object postStatement(String statement) {
    Query query = new Query(statement);
    queries.put(query.getQueryId(), query);
    return query;
  }
}
""",
                encoding="utf-8",
            )

            growth, associations = source_backed_same_handler_growth(
                (self._entry(registration_callable="com.facebook.airlift.jaxrs.JaxrsBinder.bind"),),
                root,
            )

            self.assertEqual(len(growth), 1, growth)
            self.assertEqual(len(associations), 1, associations)
            self.assertEqual(growth[0]["site_start_line"], 10)
            self.assertEqual(growth[0]["growth_kind"], "container_growth")
            self.assertEqual(growth[0]["receiver"], "example.StatementResource.queries")
            self.assertEqual(growth[0]["field_path"], "queries")
            self.assertEqual(growth[0]["demand_input_name"], "query.getQueryId()")
            self.assertEqual(growth[0]["demand_input_role"], "key")
            self.assertEqual(growth[0]["coverage_status"], "partial")
            self.assertEqual(associations[0]["confidence"], "partial")
            self.assertEqual(associations[0]["coverage_status"], "partial")
            self.assertEqual(associations[0]["source_start_line"], 8)
            self.assertEqual(associations[0]["sink_start_line"], 10)

    def test_lookalike_registration_is_not_supplemented(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "module" / "src" / "main" / "java" / "example" / "StatementResource.java"
            source.parent.mkdir(parents=True)
            source.write_text(
                """package example;
import java.util.Map;
public class StatementResource {
  private final Map<String, Object> queries = null;
  public Object postStatement(String statement) {
    queries.put(statement, new Object());
    return null;
  }
}
""",
                encoding="utf-8",
            )

            growth, associations = source_backed_same_handler_growth(
                (self._entry(registration_callable="example.JaxrsBinder.bind"),),
                root,
            )

            self.assertEqual(growth, [])
            self.assertEqual(associations, [])


if __name__ == "__main__":
    unittest.main()
