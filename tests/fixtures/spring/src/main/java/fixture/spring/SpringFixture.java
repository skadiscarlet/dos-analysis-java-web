package fixture.spring;

import org.springframework.web.bind.annotation.*;
import javax.annotation.security.PermitAll;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
class HttpServletRequest {} class Model {} class BindingResult {}

@RestController
public class SpringFixture {
    private static final Map<String, byte[]> LOOP_ITEMS = new HashMap<>();
    private final ExecutorService exactExecutor = Executors.newSingleThreadExecutor();
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

    @PermitAll
    @PostMapping("/request-local-loop")
    public void requestLocalLoop(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<String, byte[]> requestLocalLoop = new HashMap<>();
        for (int index = 0; index < count; index++) {
            requestLocalLoop.put(count + ":" + index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-exact-induction")
    public void requestLocalExactInduction(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Integer, byte[]> requestLocalExactInduction = new HashMap<>();
        for (int index = 0; index < count; index++)
            requestLocalExactInduction.put(index, body);
    }

    @PermitAll
    @PostMapping("/async-exact-loop")
    public void asyncExactLoop(@RequestParam("count") int count, @RequestBody byte[] body) {
        for (int index = 0; index < count; index++)
            exactExecutor.execute(() -> consume(body));
    }

    @PermitAll
    @PostMapping("/request-local-byte-cyclic")
    public void requestLocalByteCyclic(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Byte, byte[]> requestLocalByteCyclic = new HashMap<>();
        for (byte index = 0; index < count; index++) {
            requestLocalByteCyclic.put(index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-float-cyclic")
    public void requestLocalFloatCyclic(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Float, byte[]> requestLocalFloatCyclic = new HashMap<>();
        for (float index = 0; index < count; index++) {
            requestLocalFloatCyclic.put(index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-long-induction")
    public void requestLocalLongInduction(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Long, byte[]> requestLocalLongInduction = new HashMap<>();
        for (long index = 0; index < count; index++) {
            requestLocalLongInduction.put(index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-non-zero-induction")
    public void requestLocalNonZeroInduction(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Integer, byte[]> requestLocalNonZeroInduction = new HashMap<>();
        for (int index = 1; index < count; index++) {
            requestLocalNonZeroInduction.put(index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-derived-bound")
    public void requestLocalDerivedBound(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Integer, byte[]> requestLocalDerivedBound = new HashMap<>();
        for (int index = 0; index < count + 1; index++) {
            requestLocalDerivedBound.put(index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-decrement")
    public void requestLocalDecrement(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Integer, byte[]> requestLocalDecrement = new HashMap<>();
        for (int index = 0; index < count; index--) {
            requestLocalDecrement.put(index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-multi-statement")
    public void requestLocalMultiStatement(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Integer, byte[]> requestLocalMultiStatement = new HashMap<>();
        for (int index = 0; index < count; index++) {
            consume(body);
            requestLocalMultiStatement.put(index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-same-key")
    public void requestLocalSameKey(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Integer, byte[]> requestLocalSameKey = new HashMap<>();
        for (int index = 0; index < count; index++) {
            requestLocalSameKey.put(count, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-fresh-each-iteration")
    public void requestLocalFreshEachIteration(@RequestParam("count") int count, @RequestBody byte[] body) {
        for (int index = 0; index < count; index++) {
            Map<String, byte[]> requestLocalFreshEachIteration = new HashMap<>();
            requestLocalFreshEachIteration.put(count + ":" + index, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-list-loop")
    public void requestLocalListLoop(@RequestParam("count") int count, @RequestBody byte[] body) {
        List<byte[]> requestLocalListLoop = new ArrayList<>();
        for (int index = 0; index < count; index++) {
            requestLocalListLoop.add(body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-list-indexed-add")
    public void requestLocalListIndexedAdd(@RequestParam("count") int count, @RequestBody byte[] body) {
        List<byte[]> requestLocalListIndexedAdd = new ArrayList<>();
        for (int index = 0; index < count; index++) {
            requestLocalListIndexedAdd.add(0, body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-list-fixed-two-attacker-bound")
    public void requestLocalListFixedTwoAttackerBound(@RequestParam("count") int count, @RequestBody byte[] body) {
        List<byte[]> requestLocalListFixedTwoAttackerBound = new ArrayList<>();
        for (int index = count - 2; index < count; index++) {
            requestLocalListFixedTwoAttackerBound.add(body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-list-fixed-two-tautology")
    public void requestLocalListFixedTwoTautology(@RequestParam("count") int count, @RequestBody byte[] body) {
        List<byte[]> requestLocalListFixedTwoTautology = new ArrayList<>();
        for (int index = 0; index < 2 && count == count; index++) {
            requestLocalListFixedTwoTautology.add(body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-list-infeasible")
    public void requestLocalListInfeasible(@RequestParam("count") int count, @RequestBody byte[] body) {
        List<byte[]> requestLocalListInfeasible = new ArrayList<>();
        for (int index = count; index < count; index++) {
            requestLocalListInfeasible.add(body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-list-infeasible-condition")
    public void requestLocalListInfeasibleCondition(@RequestParam("count") int count, @RequestBody byte[] body) {
        List<byte[]> requestLocalListInfeasibleCondition = new ArrayList<>();
        for (int index = 0; index < count && false; index++) {
            requestLocalListInfeasibleCondition.add(body);
        }
    }

    @PermitAll
    @PostMapping("/request-local-conditional-map")
    public void requestLocalConditionalMap(@RequestParam("count") int count, @RequestBody byte[] body) {
        Map<Integer, byte[]> requestLocalConditionalMap = new HashMap<>();
        for (int index = 0; index < count; index++) {
            if (false) {
                requestLocalConditionalMap.put(index, body);
            }
        }
    }

    @PermitAll
    @PostMapping("/request-local-conditional-list")
    public void requestLocalConditionalList(@RequestParam("count") int count, @RequestBody byte[] body) {
        List<byte[]> requestLocalConditionalList = new ArrayList<>();
        for (int index = 0; index < count; index++) {
            if (false) {
                requestLocalConditionalList.add(body);
            }
        }
    }

    @PermitAll
    @PostMapping("/request-local-once")
    public void requestLocalOnce(@RequestParam("key") String key, @RequestBody byte[] body) {
        Map<String, byte[]> requestLocalOnce = new HashMap<>();
        requestLocalOnce.put(key, body);
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
