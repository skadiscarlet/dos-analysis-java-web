package com.google.inject;
public class Binder {
    public <T> LinkedBindingBuilder<T> bind(Class<T> type) { return new LinkedBindingBuilder<>(); }
}
