from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from dosweb.entries.jaxrs_source import augment_source_backed_jaxrs_entries


class SourceBackedJaxRsEntryTests(unittest.TestCase):
    def _write_sisu_named_module_tree(
        self,
        root: Path,
        *,
        duplicate_install: bool = False,
        duplicate_binding: bool = False,
        wildcard_helper_import: bool = False,
        non_singleton_scope: bool = False,
    ) -> None:
        java = root / "server" / "src" / "main" / "java" / "fixture"
        java.mkdir(parents=True)
        (java / "Main.java").write_text(
            """package fixture;
import org.eclipse.sisu.space.BeanScanning;
import org.eclipse.sisu.space.SpaceModule;
import org.eclipse.sisu.space.URLClassSpace;
import org.eclipse.sisu.wire.WireModule;
public class Main {
  Object modules(ClassLoader loader) {
    return new WireModule(new SpaceModule(new URLClassSpace(loader), BeanScanning.GLOBAL_INDEX));
  }
}
""",
            encoding="utf-8",
        )
        installs = "binder.install(new ChildModule());"
        if duplicate_install:
            installs += "\n    binder.install(new ChildModule());"
        (java / "RootModule.java").write_text(
            f"""package fixture;
import com.google.inject.Binder;
import com.google.inject.Module;
import javax.inject.Named;
@Named
public class RootModule implements Module {{
  public void configure(Binder binder) {{
    {installs}
  }}
}}
""",
            encoding="utf-8",
        )
        bindings = "bindJaxRsResource(binder, BinaryResource.class);"
        if duplicate_binding:
            bindings += "\n    bindJaxRsResource(binder, BinaryResource.class);"
        (java / "ChildModule.java").write_text(
            f"""package fixture;
import com.google.inject.Binder;
import com.google.inject.Module;
import static fixture.Bindings.{"*" if wildcard_helper_import else "bindJaxRsResource"};
public class ChildModule implements Module {{
  public void configure(Binder binder) {{
    {bindings}
  }}
}}
""",
            encoding="utf-8",
        )
        scope = "OTHER_SCOPE" if non_singleton_scope else "SINGLETON"
        (java / "Bindings.java").write_text(
            """package fixture;
import com.google.inject.Binder;
import static com.google.inject.Scopes.SINGLETON;
import static com.google.inject.multibindings.Multibinder.newSetBinder;
public class Bindings {
  private static final Object OTHER_SCOPE = new Object();
  public static void bindJaxRsResource(Binder binder, Class<? extends Component> klass) {
    binder.bind(klass).in(""" + scope + """);
    newSetBinder(binder, Component.class).addBinding().to(klass);
  }
}
""",
            encoding="utf-8",
        )
        (java / "Component.java").write_text(
            "package fixture; public interface Component {}\n",
            encoding="utf-8",
        )
        (java / "BinaryResource.java").write_text(
            """package fixture;
import jakarta.ws.rs.*;
import java.io.InputStream;
@Path("/api/v2/tasks")
public class BinaryResource {
  @POST
  @Path("{id}/segments/{segmentId}/data")
  @RequestBody(content = @Content(schema = @Schema(type = "string")))
  public void append(InputStream data) {}
}
""",
            encoding="utf-8",
        )

    def test_sisu_named_guice_child_helper_registration_is_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_sisu_named_module_tree(root)

            rows = augment_source_backed_jaxrs_entries([], root)

            self.assertEqual(len(rows), 1, rows)
            self.assertEqual(rows[0]["handler_fqn"], "fixture.BinaryResource.append")
            self.assertEqual(
                rows[0]["route_or_event"],
                "POST /api/v2/tasks/{id}/segments/{segmentId}/data",
            )
            self.assertEqual(rows[0]["attacker_input_name"], "data")
            self.assertEqual(rows[0]["attacker_input_kind"], "stream")
            self.assertEqual(rows[0]["coverage_status"], "complete")
            self.assertEqual(
                rows[0]["coverage_note"], "sisu_named_guice_source_registration"
            )
            self.assertEqual(
                rows[0]["registration_fqn"], "fixture.Bindings.bindJaxRsResource"
            )

    def test_sisu_duplicate_child_install_is_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_sisu_named_module_tree(root, duplicate_install=True)

            self.assertEqual(augment_source_backed_jaxrs_entries([], root), [])

    def test_sisu_duplicate_helper_binding_is_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_sisu_named_module_tree(root, duplicate_binding=True)

            self.assertEqual(augment_source_backed_jaxrs_entries([], root), [])

    def test_sisu_static_wildcard_helper_registration_is_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_sisu_named_module_tree(root, wildcard_helper_import=True)

            rows = augment_source_backed_jaxrs_entries([], root)

            self.assertEqual(len(rows), 1, rows)
            self.assertEqual(rows[0]["handler_fqn"], "fixture.BinaryResource.append")
            self.assertEqual(
                rows[0]["registration_fqn"], "fixture.Bindings.bindJaxRsResource"
            )

    def test_sisu_non_singleton_helper_is_not_promoted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_sisu_named_module_tree(root, non_singleton_scope=True)

            self.assertEqual(augment_source_backed_jaxrs_entries([], root), [])

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
