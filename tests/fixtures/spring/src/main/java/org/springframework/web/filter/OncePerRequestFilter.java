package org.springframework.web.filter;

import javax.servlet.http.HttpServletRequest;

public abstract class OncePerRequestFilter {
    protected abstract void doFilterInternal(HttpServletRequest request);
}
