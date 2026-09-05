package io.grpc;

@SuppressWarnings("unchecked")
public class ForwardingServerBuilder<T extends ServerBuilder<T>> extends ServerBuilder<T> {
    @Override public T addService(BindableService service) { return (T) this; }
    @Override public T addHandler(BindableService service) { return (T) this; }
}
