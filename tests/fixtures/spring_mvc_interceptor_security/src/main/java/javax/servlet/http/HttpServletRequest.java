package javax.servlet.http;

public interface HttpServletRequest extends javax.servlet.ServletRequest {
    String getRequestURI();
    String getHeader(String name);
}
