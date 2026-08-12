package fixture.armeria;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Optional;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Post { String value(); }
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Get { String value(); }

class HttpRequest {}
class HttpResponse {}
class ServerBuilder {
    void annotatedService(Object service) {}
}

public class ArmeriaFixture {
    void configure(ServerBuilder builder, Optional<RegisteredCollector> collector) {
        builder.annotatedService(collector.get());
    }
}

class RegisteredCollector {
    @Post("/api/v2/spans")
    public HttpResponse uploadSpans(HttpRequest request) { return new HttpResponse(); }

    @Get("/api/v2/spans")
    public HttpResponse querySpans(HttpRequest request) { return new HttpResponse(); }
}

class UnregisteredCollector {
    @Post("/not/registered")
    public HttpResponse uploadSpans(HttpRequest request) { return new HttpResponse(); }
}

class DynamicArmeriaRegistration {
    void configure(ServerBuilder builder, Object service) {
        builder.annotatedService(service);
    }
}

class FakeServerBuilder { void annotatedService(Object service) {} }
class FakeArmeriaLookalike {
    @Post("/fake")
    public HttpResponse fake(HttpRequest request) { return new HttpResponse(); }
    void configure(FakeServerBuilder builder) { builder.annotatedService(this); }
}
