package org.springframework.util;

import java.io.InputStream;
import java.nio.charset.Charset;

public final class StreamUtils {
    private StreamUtils() {}

    public static byte[] copyToByteArray(InputStream input) {
        return new byte[0];
    }

    public static String copyToString(InputStream input, Charset charset) {
        return "";
    }
}
