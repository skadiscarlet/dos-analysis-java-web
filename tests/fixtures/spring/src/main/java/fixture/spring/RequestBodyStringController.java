package fixture.spring;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RequestBodyStringController {
    @PostMapping("/string-body")
    void stringBody(@RequestBody java.lang.String body) {}

    @PostMapping("/unannotated-string")
    void unannotatedString(java.lang.String body) {}

    @PostMapping("/string-lookalike")
    void stringLookalike(@RequestBody StringLike body) {}

    static final class StringLike {}
}
