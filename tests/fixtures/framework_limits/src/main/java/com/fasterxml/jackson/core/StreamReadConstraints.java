package com.fasterxml.jackson.core;

public final class StreamReadConstraints {
    public static Builder builder() { return new Builder(); }
    public void validateStringLength(int length) {}

    public static final class Builder {
        public Builder maxStringLength(int value) { return this; }
        public StreamReadConstraints build() { return new StreamReadConstraints(); }
    }
}
