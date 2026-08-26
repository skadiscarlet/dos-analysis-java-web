package javax.servlet.http;

import java.io.ByteArrayInputStream;
import java.io.InputStream;

public class HttpServletRequest {
    public InputStream getInputStream() {
        return new ByteArrayInputStream(new byte[0]);
    }

    public HttpSession getSession() {
        return new HttpSession();
    }
}
