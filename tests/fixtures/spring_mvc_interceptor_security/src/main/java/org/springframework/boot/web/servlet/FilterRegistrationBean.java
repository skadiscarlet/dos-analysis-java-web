package org.springframework.boot.web.servlet;

import javax.servlet.Filter;

public class FilterRegistrationBean<T extends Filter> {
    public void setFilter(T filter) {}
    public void addUrlPatterns(String... patterns) {}
    public void setOrder(int order) {}
}
