package org.springframework.util;
import java.io.*;
import java.nio.charset.Charset;
public final class StreamUtils {
    public static byte[] copyToByteArray(InputStream input) throws IOException { return input.readAllBytes(); }
    public static String copyToString(InputStream input, Charset charset) throws IOException { return new String(input.readAllBytes(), charset); }
}
