package org.springframework.boot.autoconfigure.condition;

public @interface ConditionalOnProperty {
    String[] name() default {};
    String[] value() default {};
    String prefix() default "";
    String havingValue() default "";
    boolean matchIfMissing() default false;
}
