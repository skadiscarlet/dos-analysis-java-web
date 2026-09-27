package javax.servlet.http;
import java.io.InputStream;
public interface HttpServletRequest {
    InputStream getInputStream() throws java.io.IOException;
    long getContentLengthLong();
}
