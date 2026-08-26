package fixture.servlet;
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletContext;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import javax.servlet.annotation.WebServlet;
import javax.annotation.security.PermitAll;
import javax.servlet.http.*;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.stereotype.Component;
import org.eclipse.jetty.ee8.servlet.ServletContextHandler;
import org.eclipse.jetty.ee8.servlet.ServletHolder;
import java.io.*;
import java.util.*;

@WebServlet("/upload")
public class ServletFixture extends HttpServlet {
    private final Map<String, byte[]> registry = new HashMap<>();
    private static final List<byte[]> globalItems = new ArrayList<>();

    @Override
    @PermitAll
    protected void doPost(HttpServletRequest request, HttpServletResponse response) {
        byte[] body = request.body();
        int requested = Integer.parseInt(request.getParameter("size"));
        byte[] allocated = new byte[requested];
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

class RegisteredStreamFilter implements Filter {
    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain) {
        chain.doFilter(request, response);
    }
}

@Component
class ComponentCachingFilter implements Filter {
    @Override
    public void doFilter(ServletRequest request, ServletResponse response, FilterChain chain) {
        if (request instanceof HttpServletRequest) {
            try {
                BodyCachingWrapper wrapped = new BodyCachingWrapper((HttpServletRequest) request);
                chain.doFilter(wrapped, response);
                return;
            } catch (IOException failure) {
                throw new IllegalStateException(failure);
            }
        }
        chain.doFilter(request, response);
    }
}

class ServletFilterConfiguration {
    void register() {
        FilterRegistrationBean<RegisteredStreamFilter> bean = new FilterRegistrationBean<>();
        bean.setFilter(new RegisteredStreamFilter());
        bean.addUrlPatterns("/api/push/*");
    }
}

class BodyCachingWrapper extends HttpServletRequestWrapper {
    private final String body;
    BodyCachingWrapper(HttpServletRequest request) throws IOException {
        super(request);
        StringBuilder builder = new StringBuilder();
        BufferedReader reader = new BufferedReader(new InputStreamReader(request.getInputStream()));
        char[] buffer = new char[128];
        int count;
        while ((count = reader.read(buffer)) > 0) {
            builder.append(buffer, 0, count);
        }
        body = builder.toString();
    }
}

class DescriptorServlet extends HttpServlet {
    protected void service(HttpServletRequest request, HttpServletResponse response) {}
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

class ForwardingServlet extends HttpServlet {
    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) {
        request.getInputStream();
    }
}

interface IoSupplier {
    byte[] get() throws IOException;
}

@WebServlet("/lambda")
class LambdaMaterializationServlet extends HttpServlet {
    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) {
        IoSupplier body = () -> request.getInputStream().readAllBytes();
    }
}

class RouterInitializer {
    private final ForwardingServlet forwardingServlet = new ForwardingServlet();

    void initialize() {
        ServletContextHandler root = new ServletContextHandler();
        ServletHolder holder = buildServletHolder(forwardingServlet);
        root.addServlet(holder, "/druid/v2/*");
    }

    private ServletHolder buildServletHolder(ForwardingServlet servlet) {
        ServletHolder holder = new ServletHolder(servlet);
        return holder;
    }
}
