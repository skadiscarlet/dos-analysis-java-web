package com.google.inject.multibindings;
import com.google.inject.Binder;
import com.google.inject.LinkedBindingBuilder;
public class Multibinder<T> {
    public static <T> Multibinder<T> newSetBinder(Binder binder, Class<T> type) { return new Multibinder<>(); }
    public LinkedBindingBuilder<T> addBinding() { return new LinkedBindingBuilder<>(); }
}
