package org.springframework.web.servlet.config.annotation;

public interface WebMvcConfigurer {
    default void addInterceptors(InterceptorRegistry registry) {}
}
