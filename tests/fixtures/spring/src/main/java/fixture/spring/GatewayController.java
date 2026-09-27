package fixture.spring;

import cn.devezhao.commons.web.ServletUtils;
import javax.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GatewayController {
    @PostMapping("/gateway")
    void gateway(HttpServletRequest request) {
        buildContext(request);
    }

    private void buildContext(HttpServletRequest request) {
        String body = ServletUtils.getRequestString(request); // generic-body-helper-parser
        StructuredParser.parse(body);
    }

    private static final class StructuredParser {
        private static Object parse(String input) {
            return input;
        }
    }
}
