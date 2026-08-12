package fixture.spring;

@interface Controller {}
@interface RestController {}
enum RequestMethod { GET, POST, PUT, DELETE, PATCH }
@interface RequestMapping { String[] value() default {}; String[] path() default {}; RequestMethod[] method() default {}; }
@interface PostMapping { String[] value() default {}; String[] path() default {}; }
@interface GetMapping { String[] value() default {}; String[] path() default {}; }
@interface RequestBody {}
@interface RequestParam { String value() default ""; }
@interface PathVariable { String value() default ""; }
@interface RequestHeader { String value() default ""; }
@interface ModelAttribute { String value() default ""; }
class HttpServletRequest {}
class BindingResult {}
class Model {}
class ByteBuffer {
    static byte[] allocate(int size) { return new byte[size]; }
}

@Controller
@RequestMapping("/api")
public class SpringFixture {
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
