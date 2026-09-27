package org.hswebframework.web.authorization.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Inherited
public @interface Authorize {
    Resource[] resources() default {};
    Dimension[] dimension() default {};
    boolean anonymous() default false;
    boolean merge() default true;
    boolean ignore() default false;
}
