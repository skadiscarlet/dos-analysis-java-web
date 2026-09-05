package fixture.jax_rs;

import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import com.google.inject.Binder;
import com.google.inject.Module;
import org.glassfish.jersey.server.ResourceConfig;
import static com.google.inject.Scopes.SINGLETON;
import static com.google.inject.multibindings.Multibinder.newSetBinder;

class UnrelatedConfig {
    void register(Class<?> resource) {}
}

interface Component {}
class SourceBindings {
    static final Object OTHER_SCOPE = new Object();
    static <T extends Component> void publish(Binder binder, Class<T> resource) {
        binder.bind(resource).in(SINGLETON);
        newSetBinder(binder, Component.class).addBinding().to(resource);
    }
}
class WrongScopeBindings {
    static <T extends Component> void publish(Binder binder, Class<T> resource) {
        binder.bind(resource).in(SourceBindings.OTHER_SCOPE);
        newSetBinder(binder, Component.class).addBinding().to(resource);
    }
}

@Path("/api")
class RegisteredResource {
    @GET
    @Path("/items/{id}")
    String get(@PathParam("id") String id) { return id; }

    @POST
    @Path("/items")
    String post(String body) { return body; }
}

@Path("/unregistered")
class UnregisteredResource {
    @GET
    String get(String body) { return body; }
}

@Path("/api/v2/tasks/")
class HelperRegisteredResource implements Component {
    @POST
    @Path("/{id}/segments/{segmentId}/data")
    void append(java.io.InputStream data) {}
}

@Path("/lookalike-helper")
class WrongScopeResource implements Component {
    @POST
    void append(java.io.InputStream data) {}
}

class SourceModule implements Module {
    @Override
    public void configure(Binder binder) {
        SourceBindings.publish(binder, HelperRegisteredResource.class);
        WrongScopeBindings.publish(binder, WrongScopeResource.class);
    }
}

class JaxRsBootstrap {
    void start(ResourceConfig config) {
        config.register(RegisteredResource.class);
    }

    void lookalike(UnrelatedConfig config) {
        config.register(RegisteredResource.class);
    }
}
