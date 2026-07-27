package fixture.servlet;

import java.util.HashMap;
import java.util.Map;
import java.util.List;
import java.util.ArrayList;

@interface WebServlet { String value(); }
class HttpServletRequest { byte[] body() { return new byte[0]; } }
class HttpServletResponse {}
class HttpServlet {
    protected void doPost(HttpServletRequest request, HttpServletResponse response) {}
}
interface ServletRegistration {}
class ServletContext {
    void addServlet(String name, String className) {}
}

@WebServlet("/items")
public class ServletFixture extends HttpServlet {
    private final Map<String, byte[]> registry = new HashMap<>();
    private static final List<byte[]> globalItems = new ArrayList<>();

    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response) {
        byte[] body = request.body();
        if (body.length > 1024) return;
        registry.put(String.valueOf(body.length), body);
        globalItems.add(body);
        Map<String, byte[]> requestLocal = new HashMap<>();
        requestLocal.put("local", body);
        try {
            requestLocal.put("done", body);
        } finally {
            registry.remove(String.valueOf(body.length));
        }
    }
}

class UnregisteredServlet extends HttpServlet {
    @Override
    protected void doPost(HttpServletRequest request, HttpServletResponse response) {}
}

class ServletLookalike {
    void doPost(Object request, Object response) {}
    void addServlet(String name, String className) {}

    void unrelatedReflection(String className) throws Exception {
        Class.forName(className);
    }
}

class DynamicServletRegistration {
    void register(String className) throws Exception {
        Class.forName(className);
    }

    void unresolvedStaticRegistration(ServletContext context, String className) {
        context.addServlet("dynamic", className);
    }
}
