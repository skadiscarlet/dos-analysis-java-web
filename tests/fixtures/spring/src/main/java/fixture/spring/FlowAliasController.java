package fixture.spring;

import java.io.IOException;
import javax.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class FlowAliasController {
    @PostMapping({"/proof", "/proof-alias"})
    void canonical(HttpServletRequest request) throws IOException {
        materialize(request);
    }

    private void materialize(HttpServletRequest request) throws IOException {
        request.getInputStream().readAllBytes();
    }

    @PostMapping("/unrelated")
    void unrelated(HttpServletRequest request) {
        request.getSession();
    }
}
