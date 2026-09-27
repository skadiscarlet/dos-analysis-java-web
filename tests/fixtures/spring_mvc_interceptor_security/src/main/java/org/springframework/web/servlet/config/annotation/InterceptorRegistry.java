package org.springframework.web.servlet.config.annotation;

import org.springframework.web.servlet.HandlerInterceptor;

public class InterceptorRegistry {
    public InterceptorRegistration addInterceptor(HandlerInterceptor interceptor) {
        return new InterceptorRegistration();
    }
}
