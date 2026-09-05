package org.apache.solr.servlet;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

/** Minimal source-backed shape of Solr's pre-handler form parser pipeline. */
@WebServlet("/*")
public class SolrServlet extends HttpServlet {
    @Override
    protected void service(HttpServletRequest request, HttpServletResponse response) {
        dispatch(request, response, false);
    }

    private void dispatch(HttpServletRequest request, HttpServletResponse response, boolean retry) {
        HttpSolrCall call = new HttpSolrCall(request);
        call.call();
    }
}

class HttpSolrCall {
    private final HttpServletRequest request;

    HttpSolrCall(HttpServletRequest request) {
        this.request = request;
    }

    void call() {
        init();
    }

    private void init() {
        new SolrRequestParsers().parse(request);
    }
}

class SolrRequestParsers {
    private final StandardRequestParser parser = new StandardRequestParser();

    void parse(HttpServletRequest request) {
        parser.parseParamsAndFillStreams(request);
    }

    static long parseFormDataContent(
            InputStream postContent, long maxLen, Map<String, String[]> map) {
        ByteArrayOutputStream keyStream = new ByteArrayOutputStream();
        long length = 0;
        try {
            for (;;) {
                int value = postContent.read();
                if (value == -1) {
                    byte[] keyBytes = keyStream.toByteArray();
                    map.put(new String(keyBytes), new String[] {""});
                    return length;
                }
                keyStream.write(value);
                length++;
                if (length > maxLen) {
                    throw new IllegalArgumentException("form body too large");
                }
            }
        } catch (java.io.IOException failure) {
            throw new IllegalStateException(failure);
        }
    }

    static class FormDataRequestParser {
        void parseParamsAndFillStreams(HttpServletRequest request) {
            parseFormDataContent(request.getInputStream(), Long.MAX_VALUE, new HashMap<>());
        }

        boolean isFormData(HttpServletRequest request) {
            return "application/x-www-form-urlencoded".equals(request.getParameter("contentType"));
        }
    }

    static class StandardRequestParser {
        private final FormDataRequestParser formdata = new FormDataRequestParser();

        void parseParamsAndFillStreams(HttpServletRequest request) {
            if (formdata.isFormData(request)) {
                formdata.parseParamsAndFillStreams(request);
            }
        }
    }
}

/** Same local growth shape without the exact Solr pre-handler identity. */
class UnrelatedRequestParsers {
    byte[] copy(InputStream input) {
        ByteArrayOutputStream unrelated = new ByteArrayOutputStream();
        unrelated.write(1);
        return unrelated.toByteArray();
    }
}
