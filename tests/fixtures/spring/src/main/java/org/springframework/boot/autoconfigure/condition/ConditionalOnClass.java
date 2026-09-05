package org.springframework.boot.autoconfigure.condition;
public @interface ConditionalOnClass { Class<?>[] value() default {}; }
