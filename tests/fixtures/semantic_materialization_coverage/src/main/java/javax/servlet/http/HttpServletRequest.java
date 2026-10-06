package javax.servlet.http;
import java.io.InputStream;
import javax.servlet.ServletRequest;
public interface HttpServletRequest extends ServletRequest {
    InputStream getInputStream() throws java.io.IOException;
    long getContentLengthLong();
    String getServletPath();
    String getContentType();
}
