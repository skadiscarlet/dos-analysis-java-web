package fixture.spring;

@interface Controller {}
@interface RequestMapping { String value() default ""; }
@interface PostMapping { String value() default ""; }
@interface RequestBody {}
@interface RequestParam { String value() default ""; }
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

    byte[] materialize(byte[] body) { return body.clone(); }
    void consume(byte[] value) {}

    public void unregisteredLookalike(byte[] body) {}

    public void dynamicGap(String controllerName) throws Exception {
        Class.forName(controllerName);
    }
}

class SpringLookalike {
    public void handle(byte[] body) {}
    byte[] materialize(byte[] body) { return body.clone(); }

    void unrelatedReflection(String className) throws Exception {
        Class.forName(className);
    }
}
