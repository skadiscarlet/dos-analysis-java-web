package io.grpc;

@SuppressWarnings("unchecked")
public class ServerBuilder<T extends ServerBuilder<T>> {
    public T addService(BindableService service) { return (T) this; }
    public T addHandler(BindableService service) { return (T) this; }
}
