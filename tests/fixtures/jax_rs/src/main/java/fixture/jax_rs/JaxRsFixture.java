package fixture.jax_rs;

import javax.ws.rs.GET;
import javax.ws.rs.POST;
import javax.ws.rs.Path;
import javax.ws.rs.PathParam;
import org.glassfish.jersey.server.ResourceConfig;

class UnrelatedConfig {
    void register(Class<?> resource) {}
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

class JaxRsBootstrap {
    void start(ResourceConfig config) {
        config.register(RegisteredResource.class);
    }

    void lookalike(UnrelatedConfig config) {
        config.register(RegisteredResource.class);
    }
}
