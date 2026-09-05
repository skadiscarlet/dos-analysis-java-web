package fixture.spring;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;

/** Models a source-backed JAX-RS resource whose annotation types are absent from CodeQL. */
class SourceStreamResource {
    public byte[] process(InputStream input) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        output.writeBytes(input.readAllBytes());
        return output.toByteArray();
    }

    public byte[] processBeyondBound(InputStream input) throws IOException {
        return firstHelper(input);
    }

    private byte[] firstHelper(InputStream input) throws IOException {
        return secondHelper(input);
    }

    private byte[] secondHelper(InputStream input) throws IOException {
        ByteArrayOutputStream deepOutput = new ByteArrayOutputStream();
        deepOutput.writeBytes(input.readAllBytes());
        return deepOutput.toByteArray();
    }

    public byte[] processParserOutput(InputStream input) throws IOException {
        return parserHelper(input);
    }

    private byte[] parserHelper(InputStream input) throws IOException {
        return renderParserOutput(input);
    }

    private byte[] renderParserOutput(InputStream input) throws IOException {
        input.available();
        ByteArrayOutputStream parserOutput = new ByteArrayOutputStream();
        parserOutput.writeBytes(serverGeneratedBytes());
        return parserOutput.toByteArray();
    }

    private byte[] serverGeneratedBytes() {
        return new byte[] {1, 2, 3};
    }
}
