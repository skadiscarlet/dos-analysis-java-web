package fixture.spring;

import cn.hutool.core.io.IoUtil;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import javax.servlet.http.HttpServletRequest;
import org.apache.commons.io.IOUtils;
import org.springframework.util.StreamUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReadAllController {
    @PostMapping("/read/hutool")
    void hutool(HttpServletRequest request) throws IOException {
        IoUtil.readBytes(request.getInputStream());
    }

    @PostMapping("/read/commons-io")
    void commonsIo(HttpServletRequest request) throws IOException {
        IOUtils.toByteArray(request.getInputStream());
    }

    @PostMapping("/read/spring-bytes")
    void springBytes(HttpServletRequest request) throws IOException {
        StreamUtils.copyToByteArray(request.getInputStream());
    }

    @PostMapping("/read/spring-string")
    void springString(HttpServletRequest request) throws IOException {
        StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8);
    }

    @PostMapping("/read/jdk")
    void jdkReadAllBytes(HttpServletRequest request) throws IOException {
        request.getInputStream().readAllBytes();
    }

    byte[] copyBufferedOutput(byte[] body) {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.write(body, 0, body.length);
        return output.toByteArray();
    }

    @PostMapping("/read/constructor")
    void constructorString(HttpServletRequest request) {
        new RequestWrapper(request);
    }

    private static final class RequestWrapper {
        RequestWrapper(HttpServletRequest request) {
            StreamUtils.copyToString(request.getInputStream(), StandardCharsets.UTF_8);
        }
    }
}
