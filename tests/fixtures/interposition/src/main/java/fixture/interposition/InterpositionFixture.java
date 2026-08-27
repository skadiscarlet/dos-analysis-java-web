package fixture.interposition;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import javax.servlet.*;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.web.bind.annotation.*;
interface Service { void accept(ServletRequest request); }
class ServiceImpl implements Service {
    private final Map<Object, Object> retained = new ConcurrentHashMap<>();
    public void accept(ServletRequest request) { retained.computeIfAbsent(request, key -> new Object()); }
}
class RegisteredFilter implements Filter {
    private final Service service = new ServiceImpl();
    public void doFilter(ServletRequest r, ServletResponse s, FilterChain c) { service.accept(r); c.doFilter(r, s); }
}
@RestController class ExactController { @PostMapping("/api/push") public void push(Object body) {} }
@RestController class OtherController { @PostMapping("/other") public void push(Object body) {} }
class Config { void configure() { FilterRegistrationBean<RegisteredFilter> bean = new FilterRegistrationBean<>(); bean.setFilter(new RegisteredFilter()); bean.addUrlPatterns("/api/push"); bean.setOrder(1); } }
interface AmbiguousService { void accept(ServletRequest request); }
class AmbiguousServiceA implements AmbiguousService {
    private final Map<Object, Object> retainedA = new ConcurrentHashMap<>();
    public void accept(ServletRequest request) { retainedA.computeIfAbsent(request, key -> new Object()); }
}
class AmbiguousServiceB implements AmbiguousService {
    private final Map<Object, Object> retainedB = new ConcurrentHashMap<>();
    public void accept(ServletRequest request) { retainedB.computeIfAbsent(request, key -> new Object()); }
}
class AmbiguousFilter implements Filter {
    private final AmbiguousService service = new AmbiguousServiceA();
    public void doFilter(ServletRequest r, ServletResponse s, FilterChain c) { service.accept(r); c.doFilter(r, s); }
}
@RestController class AmbiguousController { @PostMapping("/api/ambiguous") public void push(Object body) {} }
class AmbiguousConfig { void configure() { FilterRegistrationBean<AmbiguousFilter> bean = new FilterRegistrationBean<>(); bean.setFilter(new AmbiguousFilter()); bean.addUrlPatterns("/api/ambiguous"); bean.setOrder(2); } }
@RestController class NoOrderController { @PostMapping("/api/no-order") public void push(Object body) {} }
class NoOrderConfig { void configure() { FilterRegistrationBean<RegisteredFilter> bean = new FilterRegistrationBean<>(); bean.setFilter(new RegisteredFilter()); bean.addUrlPatterns("/api/no-order"); } }

interface PathService { void accept(String first, String second); }
class UniquePathService implements PathService {
    private final Map<Object, Object> retainedPaths = new ConcurrentHashMap<>();
    public void accept(String first, String second) {
        retainedPaths.computeIfAbsent(first + "_" + second, key -> new Object());
    }
}
class ConstructorInjectedFilter implements Filter {
    private static final Pattern PATH = Pattern.compile("/api/constructor/([^/]+)/([^/]+)");
    private final PathService service;
    ConstructorInjectedFilter(PathService service) { this.service = service; }
    public void doFilter(ServletRequest r, ServletResponse s, FilterChain c) {
        Matcher matcher = PATH.matcher(r.getRequestURI());
        if (matcher.matches()) {
            service.accept(matcher.group(1), matcher.group(2));
        }
        c.doFilter(r, s);
    }
}
@RestController class ConstructorController { @PostMapping("/api/constructor") public void push(Object body) {} }
class ConstructorConfig {
    void configure() {
        FilterRegistrationBean<ConstructorInjectedFilter> bean = new FilterRegistrationBean<>();
        bean.setFilter(new ConstructorInjectedFilter(new UniquePathService()));
        bean.addUrlPatterns("/api/constructor");
        bean.setOrder(3);
    }
}
