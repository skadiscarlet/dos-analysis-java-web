package fixture.lombok;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import javax.servlet.*;
import javax.servlet.http.*;
import lombok.SneakyThrows;
import org.springframework.util.StreamUtils;

class LombokMetadataFilter implements Filter {
    @Override public void doFilter(ServletRequest raw, ServletResponse response, FilterChain chain) throws IOException {
        if (raw instanceof HttpServletRequest) {
            HttpServletRequest request = (HttpServletRequest) raw;
            if (request.getServletPath().contains("/api") && "application/json".equals(request.getContentType())) {
                chain.doFilter(new LombokMetadataWrapper(request), response);
                return;
            }
        }
        chain.doFilter(raw, response);
    }
}

class LombokMetadataWrapper extends HttpServletRequestWrapper {
    final String body;
    @SneakyThrows
    LombokMetadataWrapper(HttpServletRequest request) {
        super(request);
        body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); // CASE:lombok-metadata
    }
}

class LombokSizeGuardFilter implements Filter {
    @Override public void doFilter(ServletRequest raw, ServletResponse response, FilterChain chain) throws IOException {
        if (raw instanceof HttpServletRequest) {
            HttpServletRequest request = (HttpServletRequest) raw;
            if (request.getContentLengthLong() > 1024) return;
            chain.doFilter(new LombokSizeGuardWrapper(request), response);
            return;
        }
        chain.doFilter(raw, response);
    }
}

class LombokSizeGuardWrapper extends HttpServletRequestWrapper {
    final String body;
    @SneakyThrows
    LombokSizeGuardWrapper(HttpServletRequest request) {
        super(request);
        body = StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8); // CASE:lombok-size-guard
    }
}
