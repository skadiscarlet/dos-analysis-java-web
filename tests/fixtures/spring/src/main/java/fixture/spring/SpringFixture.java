package fixture.spring;

import org.springframework.web.bind.annotation.*;
import javax.annotation.security.PermitAll;
import java.nio.ByteBuffer;
import java.util.HashMap;
import java.util.Map;
class HttpServletRequest {} class Model {} class BindingResult {}

@RestController
public class SpringFixture {
    private static final Map<String, byte[]> LOOP_ITEMS = new HashMap<>();
    @PermitAll
    @PostMapping("/items")
    public void handle(@RequestBody byte[] body, @RequestParam("limit") int limit) {
        if (body.length > limit) return;
        materialize(body);
        ByteBuffer.allocate(limit);
        byte[] directArray = new byte[limit];
        consume(directArray);
        try {
            consume(body);
        } finally {
            body = null;
        }
    }

    @PermitAll
    @PostMapping("/loop")
    public void attackerControlledLoop(@RequestParam("count") int count, @RequestBody byte[] body) {
        for (int index = 0; index < count; index++) {
            LOOP_ITEMS.put(count + ":" + index, body);
        }
    }

    @PermitAll
    @PostMapping("/fixed-loop")
    public void fixedLoop(@RequestBody byte[] body) {
        for (int index = 0; index < 2; index++) {
            LOOP_ITEMS.put("fixed:" + index, body);
        }
    }

    @GetMapping({"/items", "/alias"})
    public void arrayRoute(HttpServletRequest request, Model model, BindingResult errors) {}

    @RequestMapping(path = "/command", method = {RequestMethod.POST})
    public void command(CommandObject command) {}

    byte[] materialize(byte[] body) { return body.clone(); }
    void consume(byte[] value) {}

    public void unregisteredLookalike(byte[] body) {}

    public void dynamicGap(String controllerName) throws Exception {
        Class.forName(controllerName);
    }
}

interface SecurityConstants {
    String AUTHENTICATE_ENDPOINT = "/rest/authenticate";
    String VERIFY_ENDPOINT_PREFIX = "/rest/verify";
}
class SecurityProperties {
    String authenticateEndpoint = SecurityConstants.AUTHENTICATE_ENDPOINT;
    String verifyEndpointPrefix = SecurityConstants.VERIFY_ENDPOINT_PREFIX;
}
@RestController
class SpelController {
    @PostMapping("#{citrusProperties.security.authenticateEndpoint}")
    void authenticate(HttpServletRequest request) {}
}

@RestController
@RequestMapping("#{citrusProperties.security.verifyEndpointPrefix}")
class SpelClassController {
    @GetMapping("/{type}")
    void image(HttpServletRequest request, @PathVariable String type) {}
}

class CommandObject {
    String value;
}

class SpringLookalike {
    public void handle(byte[] body) {}
    byte[] materialize(byte[] body) { return body.clone(); }

    void unrelatedReflection(String className) throws Exception {
        Class.forName(className);
    }
}
