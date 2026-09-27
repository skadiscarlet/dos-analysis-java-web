package javax.servlet.http;

import java.util.Map;

public interface HttpServletRequest {
    Map<String, String[]> getParameterMap();
}
