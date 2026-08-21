package fixture.grpc;

import io.grpc.BindableService;
import io.grpc.ServerBuilder;
import io.grpc.stub.StreamObserver;
import io.grpc.stub.annotations.GrpcGenerated;

class Request {}
class Reply {}

// Generated-code shape retained in the fixture: the source implementations
// below must override these declarations and use this generic SERVICE_NAME.
class SampleGrpc {
    static final String SERVICE_NAME = "example.Sample";

    abstract static class SampleImplBase implements BindableService {
        Reply unary(Request request, StreamObserver<Reply> observer) { return new Reply(); }
        StreamObserver<Request> collect(StreamObserver<Reply> observer) { return null; }
    }
}

class RegisteredService extends SampleGrpc.SampleImplBase {
    @Override
    Reply unary(Request request, StreamObserver<Reply> observer) {
        observer.onNext(new Reply());
        return new Reply();
    }
}

// Modern generated gRPC code exposes RPC declarations through a nested
// AsyncService interface; the concrete base merely implements that interface.
@GrpcGenerated
class ModernGrpc {
    static final String SERVICE_NAME = "example.Modern";
    interface AsyncService {
        default StreamObserver<Request> collect(StreamObserver<Reply> observer) { return null; }
    }
    abstract static class ModernImplBase implements BindableService, AsyncService {}
}
class ModernCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}
class ModernAsyncService extends ModernGrpc.ModernImplBase {
    @Override public StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new ModernCollector(); }
}

// This separate modern identity goes through an interface with two concrete
// wrappers. It must remain partial even though both eventually reach the exact
// ForwardingServerBuilder native declaration.
@GrpcGenerated
class AmbiguousModernGrpc {
    static final String SERVICE_NAME = "example.AmbiguousModern";
    interface AsyncService {
        default StreamObserver<Request> collect(StreamObserver<Reply> observer) { return null; }
    }
    abstract static class ModernImplBase implements BindableService, AsyncService {}
}
class AmbiguousModernCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}
class AmbiguousModernAsyncService extends AmbiguousModernGrpc.ModernImplBase {
    @Override public StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new AmbiguousModernCollector(); }
}

// Same conventional names and SERVICE_NAME but no generator annotation: this
// lookalike must produce neither complete entry nor partial generated-RPC gap.
class FooGrpc {
    static final String SERVICE_NAME = "example.Foo";
    interface AsyncService {
        default StreamObserver<Request> collect(StreamObserver<Reply> observer) { return null; }
    }
    abstract static class FooImplBase implements BindableService, AsyncService {}
}
class FooCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}
class FooAsyncService extends FooGrpc.FooImplBase {
    @Override public StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new FooCollector(); }
}

@GrpcGenerated
class ForwardingModernGrpc {
    static final String SERVICE_NAME = "example.ForwardingModern";
    interface AsyncService {
        default StreamObserver<Request> collect(StreamObserver<Reply> observer) { return null; }
    }
    abstract static class ModernImplBase implements BindableService, AsyncService {}
}
class ForwardingModernCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}
class ForwardingModernAsyncService extends ForwardingModernGrpc.ModernImplBase {
    @Override public StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new ForwardingModernCollector(); }
}
class FixtureForwardingServerBuilder extends io.grpc.ForwardingServerBuilder<FixtureForwardingServerBuilder> {}

class UnregisteredService extends SampleGrpc.SampleImplBase {
    @Override
    Reply unary(Request request, StreamObserver<Reply> observer) { return new Reply(); }
}

class RequestCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}

class AlternateCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}
class TernaryFirstCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}
class TernarySecondCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}
class UnsupportedGoodCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}

class RegisteredClientStreamingService extends SampleGrpc.SampleImplBase {
    @Override
    StreamObserver<Request> collect(StreamObserver<Reply> responseObserver) {
        return new RequestCollector();
    }
}

class UnregisteredClientStreamingService extends SampleGrpc.SampleImplBase {
    @Override
    StreamObserver<Request> collect(StreamObserver<Reply> responseObserver) {
        return new RequestCollector();
    }
}

class TernaryStreamingService extends SampleGrpc.SampleImplBase {
    @Override
    StreamObserver<Request> collect(StreamObserver<Reply> responseObserver) {
        return System.currentTimeMillis() == 0 ? new TernaryFirstCollector() : new TernarySecondCollector();
    }
}

// Same-shaped helpers are deliberately registered but are not generated-RPC
// overrides, so neither may become an entry.
class RegisteredHelper implements BindableService {
    Reply unary(Request request, StreamObserver<Reply> observer) { return new Reply(); }
    StreamObserver<Request> collect(StreamObserver<Reply> responseObserver) { return new RequestCollector(); }
}

class ObserverLookalike<T> { void onNext(T value) {} }
class LookalikeService extends SampleGrpc.SampleImplBase {
    @Override
    StreamObserver<Request> collect(StreamObserver<Reply> responseObserver) { return new RequestCollector(); }
    ObserverLookalike<Request> helper(ObserverLookalike<Reply> observer) { return new ObserverLookalike<Request>(); }
}

// The normal path deliberately crosses an interface dispatch and two source
// wrappers before reaching a NettyServerBuilder native registration.
interface ServiceRegister { void addHandler(BindableService service); }
interface ForwardingRegister { void addHandler(BindableService service); }
class ForwardingRegisterOne implements ForwardingRegister {
    private final io.grpc.ForwardingServerBuilder server;
    ForwardingRegisterOne(io.grpc.ForwardingServerBuilder server) { this.server = server; }
    @Override public void addHandler(BindableService service) { server.addService(service); }
}
class ForwardingRegisterTwo implements ForwardingRegister {
    private final io.grpc.ForwardingServerBuilder server;
    ForwardingRegisterTwo(io.grpc.ForwardingServerBuilder server) { this.server = server; }
    @Override public void addHandler(BindableService service) { server.addService(service); }
}
class GrpcServer {
    private final ServerBuilder server;
    GrpcServer(ServerBuilder server) { this.server = server; }
    void addHandler(BindableService service) { server.addService(service); }
}
class RegisterImpl implements ServiceRegister {
    private final GrpcServer server;
    RegisterImpl(GrpcServer server) { this.server = server; }
    @Override public void addHandler(BindableService service) { server.addHandler(service); }
}

class NoForwardingRegister { void addHandler(BindableService service) {} }
class ReflectiveRegister { void addHandler(BindableService service) { service.toString(); } }
// This has two parameter-preserving registration-relevant calls and must fail.
class AmbiguousForwardingRegister {
    private final ServerBuilder first;
    private final ServerBuilder second;
    AmbiguousForwardingRegister(ServerBuilder first, ServerBuilder second) { this.first = first; this.second = second; }
    void addHandler(BindableService service) { first.addService(service); second.addService(service); }
}
interface MultiRegister { void addHandler(BindableService service); }
class MultiRegisterOne implements MultiRegister { public void addHandler(BindableService service) {} }
class MultiRegisterTwo implements MultiRegister { public void addHandler(BindableService service) {} }

// Bad registration cases use a separate generated identity. This makes a
// complete Sample route unable to mask a partial-registration assertion.
class PartialGrpc {
    static final String SERVICE_NAME = "example.Partial";
    abstract static class PartialImplBase implements BindableService {
        StreamObserver<Request> collect(StreamObserver<Reply> observer) { return null; }
    }
}
class PartialCollector implements StreamObserver<Request> {
    @Override public void onNext(Request request) {}
}
// Each bad-registration service has generated identity and a supported observer.
class NoForwardService extends PartialGrpc.PartialImplBase {
    @Override StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new PartialCollector(); }
}
class ReflectionService extends PartialGrpc.PartialImplBase {
    @Override StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new PartialCollector(); }
}
class MixedForwardService extends PartialGrpc.PartialImplBase {
    @Override StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new PartialCollector(); }
}
class MultiImplementationService extends PartialGrpc.PartialImplBase {
    @Override StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new PartialCollector(); }
}
class DuplicateRegistrationService extends PartialGrpc.PartialImplBase {
    @Override StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new PartialCollector(); }
}
// Unsupported return leaves must remain partial, not leak their good branch.
class UnsupportedLeafService extends SampleGrpc.SampleImplBase {
    @Override StreamObserver<Request> collect(StreamObserver<Reply> responseObserver) {
        return System.currentTimeMillis() == 0 ? new UnsupportedGoodCollector() : null;
    }
}
class NoIdentityGrpc {
    abstract static class NoIdentityImplBase implements BindableService {
        StreamObserver<Request> collect(StreamObserver<Reply> observer) { return null; }
    }
}
class NoIdentityService extends NoIdentityGrpc.NoIdentityImplBase {
    @Override StreamObserver<Request> collect(StreamObserver<Reply> observer) { return new RequestCollector(); }
}

// An application subclass may override addService without forwarding to gRPC.
// Its same-named method must never count as a native registration sink.
class FakeBuilderGrpc {
    static final String SERVICE_NAME = "example.FakeBuilder";
    abstract static class FakeBuilderImplBase implements BindableService {
        Reply unary(Request request, StreamObserver<Reply> observer) { return new Reply(); }
    }
}
class FakeBuilderService extends FakeBuilderGrpc.FakeBuilderImplBase {
    @Override Reply unary(Request request, StreamObserver<Reply> observer) { return new Reply(); }
}
class FakeBuilder extends ServerBuilder<FakeBuilder> {
    @Override public FakeBuilder addService(BindableService service) { return this; }
}

class GrpcBootstrap {
    void start(ServerBuilder server) {
        server.addService(new RegisteredService());
        server.addService(new RegisteredHelper());
        server.addService(new RegisteredClientStreamingService());
        server.addService(new ModernAsyncService());
        // Registered lookalike remains outside generated-RPC coverage.
        server.addService(new FooAsyncService());
    }
    void startForwarding(FixtureForwardingServerBuilder server) {
        server.addService(new ForwardingModernAsyncService());
    }
    void startFakeBuilder(FakeBuilder server) {
        server.addService(new FakeBuilderService());
    }
    void startNetty() {
        ServiceRegister register = new RegisterImpl(new GrpcServer(new io.grpc.netty.NettyServerBuilder()));
        register.addHandler(new TernaryStreamingService()); // two supported ternary leaves
    }
    void negatives(NoForwardingRegister noForward, ReflectiveRegister reflective, AmbiguousForwardingRegister ambiguous,
                   MultiRegister multi, ServerBuilder server) {
        noForward.addHandler(new UnregisteredClientStreamingService());
        noForward.addHandler(new NoForwardService());
        reflective.addHandler(new ReflectionService());
        ambiguous.addHandler(new MixedForwardService());
        multi.addHandler(new MultiImplementationService());
        multi.addHandler(new NoIdentityService());
        ForwardingRegister forwarding = new ForwardingRegisterOne(new FixtureForwardingServerBuilder());
        forwarding.addHandler(new AmbiguousModernAsyncService());
        // Two registrations for the same generated service must not be complete.
        server.addService(new DuplicateRegistrationService());
        server.addService(new DuplicateRegistrationService());
        // Kept as an independent unsupported-return negative.
        reflective.addHandler(new UnsupportedLeafService());
        ambiguous.addHandler(new LookalikeService());
    }
    void lookalike(UnrelatedBuilder builder) { builder.addService(new RegisteredService()); }
}

class UnrelatedBuilder { void addService(Object service) {} }
