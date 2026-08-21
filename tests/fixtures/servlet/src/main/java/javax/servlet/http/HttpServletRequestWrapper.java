package javax.servlet.http;
public class HttpServletRequestWrapper extends HttpServletRequest {
    protected final HttpServletRequest request;
    public HttpServletRequestWrapper(HttpServletRequest request){ this.request = request; }
}
