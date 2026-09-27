package fixture.derived;

public final class DerivedMaterializationFixture {
    interface HttpServletRequest { }

    static final class RequestReaders {
        static String getRequestString(HttpServletRequest request) { return request.toString(); }
        static String getRequestURI(HttpServletRequest request) { return request.toString(); }
        static String getQueryString(HttpServletRequest request) { return request.toString(); }
        static String getHeader(HttpServletRequest request) { return request.toString(); }
        static String getCookie(HttpServletRequest request) { return request.toString(); }
        static String getSession(HttpServletRequest request) { return request.toString(); }
    }

    static final class ParsedTree { }

    static final class StructuredParser {
        static ParsedTree parse(String input) { return new ParsedTree(); }
    }

    static final class BinaryEncoder {
        boolean[] encode(String input) { return new boolean[input.length()]; }
    }

    static final class PixelMatrix { }
    static final class RasterImage { }

    static final class MatrixRenderer {
        static PixelMatrix render(String input, int width, int height) {
            return new PixelMatrix();
        }
    }

    static final class ImageMaterializer {
        static RasterImage toImage(PixelMatrix matrix) { return new RasterImage(); }
    }

    void bodyHelperThenParser(HttpServletRequest request) {
        String body = RequestReaders.getRequestString(request); // body-helper-positive
        ParsedTree parsed = StructuredParser.parse(body);
        consume(parsed);
    }

    void metadataLookalikes(HttpServletRequest request) {
        consume(StructuredParser.parse(RequestReaders.getRequestURI(request))); // uri-negative
        consume(StructuredParser.parse(RequestReaders.getQueryString(request))); // query-negative
        consume(StructuredParser.parse(RequestReaders.getHeader(request))); // header-negative
        consume(StructuredParser.parse(RequestReaders.getCookie(request))); // cookie-negative
        consume(StructuredParser.parse(RequestReaders.getSession(request))); // session-negative
    }

    void derivedDimension(String content, int height) {
        int width = (int) (new BinaryEncoder().encode(content).length * 1.5); // derived-positive
        PixelMatrix matrix = MatrixRenderer.render(content, width, height); // materializer-positive
        consume(ImageMaterializer.toImage(matrix));
    }

    void ordinaryEncodedLength(String content) {
        int width = new BinaryEncoder().encode(content).length; // ordinary-length-negative
        consume(width);
    }

    void capAfterDerivation(String content, int height) {
        int width = new BinaryEncoder().encode(content).length; // cap-after-derivation
        width = Math.min(width, 1024); // effective-post-derivation-cap
        PixelMatrix matrix = MatrixRenderer.render(content, width, height); // cap-after-materializer
        consume(ImageMaterializer.toImage(matrix));
    }

    void capBeforeOverwrite(String content, int height) {
        int width = Math.min(content.length(), 1024); // stale-pre-derivation-cap
        width = new BinaryEncoder().encode(content).length; // overwrite-after-cap
        PixelMatrix matrix = MatrixRenderer.render(content, width, height); // cap-before-materializer
        consume(ImageMaterializer.toImage(matrix));
    }

    private static void consume(Object value) { }
    private static void consume(int value) { }
}
