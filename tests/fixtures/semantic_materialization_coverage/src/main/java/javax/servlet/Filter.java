package javax.servlet;
public interface Filter {
    void doFilter(ServletRequest request, ServletResponse response, FilterChain chain) throws java.io.IOException;
}
