package fixture.interceptor;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.HandlerInterceptor;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;
import org.springframework.web.method.HandlerMethod;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import javax.servlet.Filter;
import javax.servlet.FilterChain;
import javax.servlet.ServletRequest;
import javax.servlet.ServletResponse;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@interface ProtectedRoute {}

class SecurityInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
        HttpServletRequest request, HttpServletResponse response, Object handler
    ) throws Exception {
        String requestUri = request.getRequestURI();
        if (!isPublicRoute(requestUri)) {
            response.sendError(401);
            return false;
        }
        return true;
    }

    private boolean isPublicRoute(String requestUri) {
        return requestUri.startsWith("/commons/barcode/render")
            || requestUri.equals("/exact-public");
    }
}

class LoggingInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
        HttpServletRequest request, HttpServletResponse response, Object handler
    ) {
        return true;
    }
}

class ForbiddenInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
        HttpServletRequest request, HttpServletResponse response, Object handler
    ) throws Exception {
        String requestUri = request.getRequestURI();
        if (!isAllowed(requestUri)) {
            response.sendError(403);
            return false;
        }
        return true;
    }

    private boolean isAllowed(String requestUri) {
        return requestUri.startsWith("/wrong-status");
    }
}

class InvertedSecurityInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
        HttpServletRequest request, HttpServletResponse response, Object handler
    ) throws Exception {
        String requestUri = request.getRequestURI();
        if (isBlocked(requestUri)) {
            response.sendError(401);
            return false;
        }
        return true;
    }

    private boolean isBlocked(String requestUri) {
        return requestUri.startsWith("/inverted");
    }
}

class AnnotationSecurityInterceptor implements HandlerInterceptor {
    @Override
    public boolean preHandle(
        HttpServletRequest request, HttpServletResponse response, Object handler
    ) throws Exception {
        ProtectedRoute route = null;
        if (handler instanceof HandlerMethod) {
            route = ((HandlerMethod) handler).getMethodAnnotation(ProtectedRoute.class);
        }
        if (route == null) {
            return true;
        }
        if (request.getHeader("token") == null) {
            response.sendError(401);
            return false;
        }
        return true;
    }
}

class OrderedBodyFilter implements Filter {
    @Override
    public void doFilter(
        ServletRequest request, ServletResponse response, FilterChain chain
    ) {
        chain.doFilter(request, response);
    }
}

class UnorderedBodyFilter implements Filter {
    @Override
    public void doFilter(
        ServletRequest request, ServletResponse response, FilterChain chain
    ) {
        chain.doFilter(request, response);
    }
}

class InterceptorFixtureConfiguration implements WebMvcConfigurer {
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new SecurityInterceptor())
            .addPathPatterns("/**")
            .excludePathPatterns("/gw/api/**");
        registry.addInterceptor(new LoggingInterceptor())
            .excludePathPatterns("/logging-only/**");
        registry.addInterceptor(new ForbiddenInterceptor())
            .excludePathPatterns("/forbidden-excluded/**");
        registry.addInterceptor(new InvertedSecurityInterceptor());
        registry.addInterceptor(new AnnotationSecurityInterceptor())
            .addPathPatterns("/**");
    }

    void registerOrderedFilter() {
        FilterRegistrationBean<OrderedBodyFilter> registration =
            new FilterRegistrationBean<>();
        registration.setFilter(new OrderedBodyFilter());
        registration.addUrlPatterns("/ordered/*");
        registration.setOrder(1);
    }

    void registerUnorderedFilter() {
        FilterRegistrationBean<UnorderedBodyFilter> registration =
            new FilterRegistrationBean<>();
        registration.setFilter(new UnorderedBodyFilter());
        registration.addUrlPatterns("/unordered/*");
    }
}

@RestController
public class InterceptorSecurityFixture {
    @GetMapping({
        "/commons/barcode/render",
        "/commons/barcode/render-qr",
        "/commons/barcode/render-auto"
    })
    public void barcode() {}

    @GetMapping("/commons/barcode/private")
    public void barcodePrivate() {}

    @GetMapping("/exact-public")
    public void exactPublic() {}

    @GetMapping("/exact-public-child")
    public void exactPublicChild() {}

    @GetMapping("/gw/api/open")
    public void excludedOpen() {}

    @GetMapping("/gw/private")
    public void excludedNegative() {}

    @GetMapping("/logging-only/open")
    public void loggingNegative() {}

    @GetMapping("/forbidden-excluded/open")
    public void forbiddenNegative() {}

    @GetMapping("/wrong-status/open")
    public void wrongStatusNegative() {}

    @GetMapping("/inverted/open")
    public void invertedNegative() {}

    @GetMapping("/ordered/open")
    public void annotationAbsentOpen() {}

    @ProtectedRoute
    @GetMapping("/ordered/protected")
    public void annotationProtected() {}

    @GetMapping("/unordered/open")
    public void unorderedAnnotationAbsentOpen() {}
}
