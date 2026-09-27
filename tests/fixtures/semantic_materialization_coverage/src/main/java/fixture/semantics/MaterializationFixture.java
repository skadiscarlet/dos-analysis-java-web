package fixture.semantics;
import java.io.*;
import javax.servlet.http.*;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.util.StreamUtils;

public class MaterializationFixture {
    @PostMapping("/plain")
    public byte[] plain(HttpServletRequest request) throws IOException {
        return request.getInputStream().readAllBytes(); // CASE:spring-plain
    }
    @PostMapping("/library")
    public byte[] library(HttpServletRequest request) throws IOException {
        return StreamUtils.copyToByteArray(request.getInputStream()); // CASE:spring-library
    }
    @PostMapping("/wrapped")
    public Object wrapper(HttpServletRequest request) throws IOException {
        return new BodyWrapper(request);
    }
    @PostMapping("/conditional")
    public byte[] conditional(HttpServletRequest request) throws IOException {
        if (request.getContentLengthLong() > 1024) return new byte[0];
        return request.getInputStream().readAllBytes(); // CASE:conditional
    }
    @PostMapping("/helper")
    public byte[] helper(HttpServletRequest request) throws IOException {
        check(request);
        return request.getInputStream().readAllBytes(); // CASE:helper
    }
    private static void check(HttpServletRequest request) throws IOException {
        if (request.getContentLengthLong() > 1024) throw new IOException();
    }
    @PostMapping("/limited")
    public byte[] limited(HttpServletRequest request) throws IOException {
        return new LimitedStream(request.getInputStream()).readAllBytes(); // CASE:limited
    }
    @PostMapping("/local")
    public byte[] local(HttpServletRequest request) throws IOException {
        ByteArrayInputStream local = new ByteArrayInputStream(new byte[8]);
        return local.readAllBytes(); // CASE:local
    }
    @PostMapping("/caller-guarded-wrapper")
    public Object callerGuardedWrapper(HttpServletRequest request) throws IOException {
        if (request.getContentLengthLong() > 1024) return null;
        return new CallerGuardedWrapper(request);
    }
    @PostMapping("/guarded-wrapper")
    public Object guardedWrapper(HttpServletRequest request) throws IOException {
        return new GuardedWrapper(request);
    }
    @PostMapping("/closed")
    public byte[] closed(HttpServletRequest request) throws IOException {
        byte[] body = request.getInputStream().readAllBytes(); // CASE:closed
        request.getInputStream().close();
        return body;
    }
    @PostMapping("/reassigned")
    public byte[] reassigned(HttpServletRequest request, HttpServletRequest other) throws IOException {
        request = other;
        return request.getInputStream().readAllBytes(); // CASE:reassigned
    }
}
class BodyWrapper extends HttpServletRequestWrapper {
    final byte[] body;
    BodyWrapper(HttpServletRequest request) throws IOException {
        super(request);
        body = request.getInputStream().readAllBytes(); // CASE:wrapper
    }
}
class GuardedWrapper extends HttpServletRequestWrapper {
    final byte[] body;
    GuardedWrapper(HttpServletRequest request) throws IOException {
        super(request);
        if (request.getContentLengthLong() > 1024) throw new IOException();
        body = request.getInputStream().readAllBytes(); // CASE:guarded-wrapper
    }
}
class LimitedStream extends FilterInputStream {
    LimitedStream(InputStream input) { super(input); }
    @Override public byte[] readAllBytes() throws IOException { return new byte[1]; }
}

class PlainServlet extends HttpServlet {
    @Override public void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        byte[] body = request.getInputStream().readAllBytes(); // CASE:plain
    }
    @Override public void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        byte[] body = StreamUtils.copyToByteArray(request.getInputStream()); // CASE:library
    }
}
class CallerGuardedWrapper extends HttpServletRequestWrapper {
    final byte[] body;
    CallerGuardedWrapper(HttpServletRequest request) throws IOException {
        super(request);
        body = request.getInputStream().readAllBytes(); // CASE:caller-guarded-wrapper
    }
}
