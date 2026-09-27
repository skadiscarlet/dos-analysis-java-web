package org.springframework.util;
import java.io.*;
public final class StreamUtils {
    public static byte[] copyToByteArray(InputStream input) throws IOException { return input.readAllBytes(); }
}
