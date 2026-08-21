package javax.servlet.http;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
public class HttpServletRequest {
    public byte[] body(){ return new byte[0]; }
    public String getParameter(String name){ return "0"; }
    public InputStream getInputStream(){ return new ByteArrayInputStream(new byte[0]); }
}
