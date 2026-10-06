package javax.servlet.http;
import java.io.InputStream;
public class HttpServletRequestWrapper implements HttpServletRequest {
    private final HttpServletRequest delegate;
    public HttpServletRequestWrapper(HttpServletRequest delegate) { this.delegate = delegate; }
    public InputStream getInputStream() throws java.io.IOException { return delegate.getInputStream(); }
    public long getContentLengthLong() { return delegate.getContentLengthLong(); }
    public String getServletPath() { return delegate.getServletPath(); }
    public String getContentType() { return delegate.getContentType(); }
}
