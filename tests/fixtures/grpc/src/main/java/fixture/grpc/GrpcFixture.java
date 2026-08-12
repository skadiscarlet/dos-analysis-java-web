package fixture.grpc;

import io.grpc.BindableService;
import io.grpc.stub.StreamObserver;
import io.grpc.ServerBuilder;
class Request {}
class Reply {}

class RegisteredService implements BindableService {
    Reply unary(Request request, StreamObserver<Reply> observer) {
        observer.onNext(new Reply());
        return new Reply();
    }
}

class UnregisteredService implements BindableService {
    Reply unary(Request request, StreamObserver<Reply> observer) { return new Reply(); }
}

class GrpcBootstrap {
    void start(ServerBuilder server) {
        server.addService(new RegisteredService());
    }

    void lookalike(UnrelatedBuilder builder) {
        builder.addService(new RegisteredService());
    }
}

class UnrelatedBuilder {
    void addService(Object service) {}
}
