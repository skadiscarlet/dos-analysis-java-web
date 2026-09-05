package cn.devezhao.commons.web;

import javax.servlet.http.HttpServletRequest;

public final class ServletUtils {
    private ServletUtils() {}

    public static String getRequestString(HttpServletRequest request) {
        return request.toString();
    }
}
