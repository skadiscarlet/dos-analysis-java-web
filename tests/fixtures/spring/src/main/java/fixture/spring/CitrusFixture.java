package fixture.spring;

import cn.hutool.core.io.IoUtil;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletRequestWrapper;
import javax.servlet.http.HttpSession;

@RestController
class CitrusAuthenticateController {
    @PostMapping("#{citrusProperties.security.authenticateEndpoint}")
    void authenticate(HttpServletRequest request) {}
}

@Component
class CitrusRequestWrapperFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request) {
        new RequestWrapper(request);
    }

    static class RequestWrapper extends HttpServletRequestWrapper {
        private final byte[] body;

        RequestWrapper(HttpServletRequest request) {
            super(request);
            body = IoUtil.readBytes(request.getInputStream());
        }
    }
}

@Component
class SkippableRequestWrapperFilter extends OncePerRequestFilter {
    @Override
    protected void doFilterInternal(HttpServletRequest request) {
        new SkippedWrapper(request);
    }

    protected boolean shouldNotFilter(HttpServletRequest request) {
        return true;
    }

    static class SkippedWrapper extends HttpServletRequestWrapper {
        SkippedWrapper(HttpServletRequest request) {
            super(request);
            IoUtil.readBytes(request.getInputStream());
        }
    }
}

interface CitrusVerificationProcessor<T> {
    void send(HttpServletRequest request);
}

interface CitrusVerificationRepository {
    void save(HttpServletRequest request, Object verification);
}

class CitrusCaptchaProcessor implements CitrusVerificationProcessor<CitrusCaptcha> {
    private final CitrusVerificationRepository repository =
        new CitrusSessionVerificationRepository();

    @Override
    public void send(HttpServletRequest request) {
        repository.save(request, new CitrusCaptcha());
    }
}

class CitrusCaptcha {}

class CitrusSessionVerificationRepository implements CitrusVerificationRepository {
    @Override
    public void save(HttpServletRequest request, Object verification) {
        HttpSession session = request.getSession();
        session.setAttribute("SESSION_VERIFY_ID", verification);
    }
}

@RestController
@RequestMapping("#{citrusProperties.security.verifyEndpointPrefix}")
class CitrusVerificationController {
    private final CitrusVerificationProcessor<?> processor = new CitrusCaptchaProcessor();

    @GetMapping("/{type}")
    void image(HttpServletRequest request, @PathVariable String type) {
        processor.send(request);
    }
}
