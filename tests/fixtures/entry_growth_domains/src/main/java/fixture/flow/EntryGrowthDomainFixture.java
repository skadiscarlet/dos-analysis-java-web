package fixture.flow;

import javax.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestParam;

import java.util.HashMap;
import java.util.Map;

public final class EntryGrowthDomainFixture {
    private static final Map<String, String> SERVER_CONTENT = new HashMap<>();

    static final class RequestReaders {
        static String readBody(HttpServletRequest request) {
            return request.toString();
        }

        static String getRequestURI(HttpServletRequest request) {
            return request.toString();
        }
    }

    static final class ParsedTree {}

    static final class StructuredParser {
        static ParsedTree parse(String input) {
            return new ParsedTree();
        }
    }

    static final class BinaryEncoder {
        boolean[] encode(String input) {
            return new boolean[input.length()];
        }
    }

    static final class PixelMatrix {}
    static final class RasterImage {}

    static final class MatrixRenderer {
        static PixelMatrix render(String input, int width, int height) {
            return new PixelMatrix();
        }
    }

    static final class ImageMaterializer {
        static RasterImage toImage(PixelMatrix matrix) {
            return new RasterImage();
        }
    }

    private static String getParameter(HttpServletRequest request, String name) {
        return request.toString();
    }

    private static String serverContentSelectedBy(String id) {
        return SERVER_CONTENT.get(id);
    }

    @PostMapping("/helper-parser")
    public void helperParser(HttpServletRequest request) {
        String body = RequestReaders.readBody(request); // helper-parser-positive
        consume(StructuredParser.parse(body));
    }

    @PostMapping("/helper-parser-metadata-guard")
    public void helperParserWithMetadataGuard(HttpServletRequest request) {
        Map<String, String> parameters = new HashMap<>();
        for (Map.Entry<String, String[]> entry : request.getParameterMap().entrySet()) {
            String[] values = entry.getValue();
            parameters.put(
                entry.getKey(), values == null || values.length == 0 ? null : values[0]
            );
        }
        requireParameter(parameters, "appid");
        String body = RequestReaders.readBody(request); // metadata-presence-helper-growth
        consume(StructuredParser.parse(body));
    }

    @PostMapping("/helper-parser-body-guard")
    public void helperParserWithBodyGuard(HttpServletRequest request) {
        requireBody(request);
        String body = RequestReaders.readBody(request); // body-size-helper-growth
        consume(StructuredParser.parse(body));
    }

    @PostMapping("/metadata")
    public void metadata(HttpServletRequest request) {
        String path = RequestReaders.getRequestURI(request); // metadata-helper-negative
        consume(StructuredParser.parse(path));
    }

    @PostMapping("/helper-without-parser")
    public void helperWithoutParser(HttpServletRequest request) {
        consume(RequestReaders.readBody(request)); // unparsed-helper-negative
    }

    @PostMapping("/derived")
    public void derived(
        @RequestBody String content,
        @RequestParam int height
    ) {
        int width = new BinaryEncoder().encode(content).length * 2;
        PixelMatrix matrix = MatrixRenderer.render(content, width, height); // derived-flow-positive
        consume(ImageMaterializer.toImage(matrix));
    }

    @PostMapping("/direct-derived-helper")
    public void directDerivedHelper(HttpServletRequest request) {
        sharedDerived(getParameter(request, "content"));
    }

    @PostMapping("/server-selected-derived")
    public void serverSelectedDerived(HttpServletRequest request) {
        String id = getParameter(request, "id");
        sharedDerived(serverContentSelectedBy(id));
    }

    private static void sharedDerived(String content) {
        int width = new BinaryEncoder().encode(content).length * 2;
        PixelMatrix matrix = MatrixRenderer.render(content, width, 64); // shared-derived-flow
        consume(ImageMaterializer.toImage(matrix));
    }

    private static void requireParameter(Map<String, String> parameters, String name) {
        String value = parameters.get(name);
        if (value == null) {
            throw new IllegalArgumentException(name);
        }
    }

    private static void requireBody(HttpServletRequest request) {
        if (request.toString().length() > 1024) {
            throw new IllegalArgumentException("body");
        }
    }

    @PostMapping("/ordinary-extent")
    public void ordinaryExtent(@RequestBody String content) {
        int width = new BinaryEncoder().encode(content).length;
        consume(width); // ordinary-extent-negative
    }

    @PostMapping("/fixed-producer")
    public void fixedProducer(
        @RequestBody String ignored,
        @RequestParam int height
    ) {
        int width = new BinaryEncoder().encode("fixed").length;
        PixelMatrix matrix = MatrixRenderer.render(ignored, width, height); // fixed-producer-negative
        consume(ImageMaterializer.toImage(matrix));
    }

    private static void consume(Object value) {}
    private static void consume(int value) {}
}
