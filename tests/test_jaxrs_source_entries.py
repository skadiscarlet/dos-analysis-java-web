from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dosweb.entries.jaxrs_source import augment_source_backed_jaxrs_entries


class SourceBackedJaxRsEntryTests(unittest.TestCase):
    def test_airlift_jaxrs_binder_registration_is_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            java = root / "presto-main" / "src" / "main" / "java" / "example"
            java.mkdir(parents=True)
            (java / "StatementResource.java").write_text(
                """package example;
import jakarta.ws.rs.*;
@Path("/")
public class StatementResource {
  @POST
  @Path("/v1/statement")
  public Object postStatement(String statement, @QueryParam("retry") String retry) {
    return null;
  }
}
""",
                encoding="utf-8",
            )
            (java / "CoordinatorModule.java").write_text(
                """package example;
import com.facebook.airlift.configuration.AbstractConfigurationAwareModule;
import com.google.inject.Binder;
import static com.facebook.airlift.jaxrs.JaxrsBinder.jaxrsBinder;
public class CoordinatorModule extends AbstractConfigurationAwareModule {
  protected void setup(Binder binder) {
    jaxrsBinder(binder).bind(StatementResource.class);
  }
}
""",
                encoding="utf-8",
            )

            rows = augment_source_backed_jaxrs_entries([], root)

            self.assertEqual(len(rows), 2, rows)
            self.assertEqual(
                {(row["attacker_input_name"], row["attacker_input_kind"]) for row in rows},
                {("statement", "request_body"), ("retry", "request_parameter")},
            )
            self.assertTrue(all(row["route_or_event"] == "POST /v1/statement" for row in rows))
            self.assertTrue(all(row["coverage_status"] == "complete" for row in rows))
            self.assertTrue(
                all(row["coverage_note"] == "airlift_jaxrs_source_registration" for row in rows)
            )
            self.assertTrue(
                all(row["registration_fqn"] == "com.facebook.airlift.jaxrs.JaxrsBinder.bind" for row in rows)
            )

    def test_custom_dropwizard_guice_lookalikes_are_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            java = root / "app" / "src" / "main" / "java" / "example"
            java.mkdir(parents=True)
            (java / "Resource.java").write_text(
                """package example;
import jakarta.ws.rs.*;
@Path("/")
public class Resource {
  @POST @Path("upload")
  public Object upload(java.io.InputStream input) { return null; }
}
""",
                encoding="utf-8",
            )
            (java / "Module.java").write_text(
                """package example;
public class Module extends DropwizardAwareModule<Object> {
  protected void configure() { bind(Resource.class); }
}
""",
                encoding="utf-8",
            )
            (java / "App.java").write_text(
                """package example;
public class App extends Application<Object> {
  public void initialize(Bootstrap<Object> bootstrap) {
    GuiceBundle bundle = GuiceBundle.builder().modules(new Module()).build();
    bootstrap.addBundle(bundle);
  }
  public void run(Object config, Environment environment) {
    environment.jersey().setUrlPattern("/api/*");
  }
}
""",
                encoding="utf-8",
            )

            self.assertEqual(augment_source_backed_jaxrs_entries([], root), [])

    def test_duplicate_application_installation_is_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            java = root / "app" / "src" / "main" / "java" / "example"
            java.mkdir(parents=True)
            (java / "Resource.java").write_text(
                """package example;
import jakarta.ws.rs.*;
@Path("/")
public class Resource {
  @POST @Path("upload")
  public Object upload(java.io.InputStream input) { return null; }
}
""",
                encoding="utf-8",
            )
            (java / "Module.java").write_text(
                """package example;
import ru.vyarus.dropwizard.guice.module.support.DropwizardAwareModule;
public class Module extends DropwizardAwareModule<Object> {
  protected void configure() { bind(Resource.class); }
}
""",
                encoding="utf-8",
            )
            application = """package example;
import io.dropwizard.core.Application;
import io.dropwizard.core.setup.Bootstrap;
import io.dropwizard.core.setup.Environment;
import ru.vyarus.dropwizard.guice.GuiceBundle;
public class {name} extends Application<Object> {{
  public void initialize(Bootstrap<Object> bootstrap) {{
    GuiceBundle bundle = GuiceBundle.builder().modules(new Module()).build();
    bootstrap.addBundle(bundle);
  }}
  public void run(Object config, Environment environment) {{
    environment.jersey().setUrlPattern("/api/*");
  }}
}}
"""
            (java / "FirstApp.java").write_text(application.format(name="FirstApp"), encoding="utf-8")
            (java / "SecondApp.java").write_text(application.format(name="SecondApp"), encoding="utf-8")

            self.assertEqual(augment_source_backed_jaxrs_entries([], root), [])

    def test_duplicate_resource_binding_is_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            java = root / "app" / "src" / "main" / "java" / "example"
            java.mkdir(parents=True)
            (java / "Resource.java").write_text(
                """package example;
import jakarta.ws.rs.*;
@Path("/")
public class Resource {
  @POST @Path("upload")
  public Object upload(java.io.InputStream input) { return null; }
}
""",
                encoding="utf-8",
            )
            (java / "Module.java").write_text(
                """package example;
import ru.vyarus.dropwizard.guice.module.support.DropwizardAwareModule;
public class Module extends DropwizardAwareModule<Object> {
  protected void configure() {
    bind(Resource.class);
    bind(Resource.class);
  }
}
""",
                encoding="utf-8",
            )
            (java / "App.java").write_text(
                """package example;
import io.dropwizard.core.Application;
import io.dropwizard.core.setup.Bootstrap;
import io.dropwizard.core.setup.Environment;
import ru.vyarus.dropwizard.guice.GuiceBundle;
public class App extends Application<Object> {
  public void initialize(Bootstrap<Object> bootstrap) {
    GuiceBundle bundle = GuiceBundle.builder().modules(new Module()).build();
    bootstrap.addBundle(bundle);
  }
  public void run(Object config, Environment environment) {
    environment.jersey().setUrlPattern("/api/*");
  }
}
""",
                encoding="utf-8",
            )

            self.assertEqual(augment_source_backed_jaxrs_entries([], root), [])


if __name__ == "__main__":
    unittest.main()
