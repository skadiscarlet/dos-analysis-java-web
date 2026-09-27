package fixture.hsweb;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.hswebframework.web.authorization.annotation.Authorize;
import org.hswebframework.web.authorization.annotation.Dimension;
import org.hswebframework.web.authorization.annotation.Resource;
import org.hswebframework.web.authorization.annotation.ResourceAction;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Authorize(anonymous = true)
@interface ComposedAnonymous {}

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Dimension(type = "role", id = "operator")
@interface OperatorOnly {}

@RestController
public class HswebDefaultSecurityFixture {
    @GetMapping("/plain")
    public void plain() {}

    public void internalHelper() {}

    @GetMapping("/anonymous")
    @Authorize(anonymous = true)
    public void anonymous() {}

    @GetMapping("/ignored")
    @Authorize(ignore = true)
    public void ignored() {}

    @GetMapping("/resource")
    @Resource(id = "device")
    public void resourceProtected() {}

    @GetMapping("/action")
    @ResourceAction(id = "read")
    public void actionProtected() {}

    @GetMapping("/composed")
    @ComposedAnonymous
    public void composedAnnotation() {}

    @GetMapping("/dimension")
    @OperatorOnly
    public void composedDimension() {}

    @GetMapping("/spring-conflict")
    @PreAuthorize("isAuthenticated()")
    public void springSecurityConflict() {}
}

@RestController
@Resource(id = "class-resource")
class ClassResourceFixture {
    @GetMapping("/class-resource")
    public void inheritedResource() {}

    @GetMapping("/class-ignore")
    @Authorize(ignore = true)
    public void methodIgnoreWins() {}
}

@RestController
@Authorize(ignore = true)
class ClassIgnoreFixture {
    @GetMapping("/class-ignore-inherited")
    public void inheritedIgnore() {}

    @GetMapping("/method-authorize")
    @Authorize
    public void methodAuthorizeOverridesClassIgnore() {}
}
