package fixture;

import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;

public class DirectAllocationEdgeFixture {
    private int serverLimit = 8;

    @RequestMapping("/multidimensional-array")
    public byte[][] multidimensionalArray(@RequestParam("width") int width) {
        return new byte[1][width];
    }

    @RequestMapping("/safe-assignment-loop")
    public void safeAssignmentLoop(@RequestParam("count") int count) {
        byte[] allocated = null;
        for (int index = 0; index < count; index++) {
            allocated = new byte[1]; // safe-assignment allocation
        }
        consume(allocated);
    }

    @RequestMapping("/argument-subexpression-loop")
    public void argumentSubexpressionLoop(@RequestParam("count") int count) {
        for (int index = 0; index < count; index++) {
            consume(new byte[1]); // argument-subexpression allocation
        }
    }

    @RequestMapping("/return-loop")
    public byte[] returnLoop(@RequestParam("count") int count) {
        for (int index = 0; index < count; index++) {
            return new byte[1]; // return allocation
        }
        return null;
    }

    @RequestMapping("/throw-loop")
    public void throwLoop(@RequestParam("count") int count) {
        for (int index = 0; index < count; index++) {
            throw new IllegalArgumentException(new String(new byte[1])); // throw allocation
        }
    }

    @RequestMapping("/conditional-rhs-loop")
    public void conditionalRhsLoop(@RequestParam("count") int count) {
        byte[] allocated = null;
        for (int index = 0; index < count; index++) {
            allocated = index >= 0 ? new byte[1] : null; // conditional-rhs allocation
        }
        consume(allocated);
    }

    @RequestMapping("/bound-mutation-loop")
    public void boundMutationLoop(@RequestParam("count") int count) {
        byte[] allocated = null;
        for (int index = 0; index < count; index++) {
            allocated = new byte[count--]; // bound-mutation allocation
        }
        consume(allocated);
    }

    @RequestMapping("/break-loop")
    public void breakLoop(@RequestParam("count") int count) {
        for (int index = 0; index < count; index++) {
            if (index == 4) {
                break;
            }
            consume(new byte[1]); // break-limited allocation
        }
    }

    @RequestMapping("/server-capped-loop")
    public void serverCappedLoop(@RequestParam("count") int count) {
        for (int index = 0; index < count && index < serverLimit; index++) {
            consume(new byte[1]); // server-capped allocation
        }
    }

    @RequestMapping("/nested-lambda-loop")
    public void nestedLambdaLoop(@RequestParam("count") int count) {
        for (int index = 0; index < count; index++) {
            Runnable task = () -> consume(new byte[1]); // nested-lambda allocation
            task.run();
        }
    }

    @RequestMapping("/nested-callable-loop")
    public void nestedCallableLoop(@RequestParam("count") int count) {
        for (int index = 0; index < count; index++) {
            Runnable task = new Runnable() {
                @Override
                public void run() {
                    consume(new byte[1]); // nested-callable allocation
                }
            };
            task.run();
        }
    }

    @RequestMapping("/unmodeled-loop")
    public void unmodeledLoop(@RequestParam("ignored") int ignored) {
        for (int index = 0; index < serverLimit; index++) {
            consume(new byte[1]); // server-only allocation
        }
    }

    private void consume(byte[] value) { }
}
