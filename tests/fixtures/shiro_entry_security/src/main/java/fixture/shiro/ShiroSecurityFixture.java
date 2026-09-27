package fixture.shiro;

import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import org.apache.shiro.spring.web.ShiroFilterFactoryBean;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

class OrderedShiroConfiguration {
    ShiroFilterFactoryBean orderedFactory() {
        ShiroFilterFactoryBean factory = new ShiroFilterFactoryBean();
        LinkedHashMap<String, String> chains = new LinkedHashMap<>();
        chains.put("/public/**", "anon");
        chains.put("/session/**", "authc");
        chains.put("/role/**", "roles[admin]");
        chains.put("/perm/**", "perms[data:read]");
        chains.put("/admin/**", "admin");
        chains.put("/conflict/**", "anon,authc");
        chains.put("/**", "user,kickout");
        chains.put("/late-public/**", "anon");
        factory.setFilterChainDefinitionMap(chains);
        return factory;
    }

    ShiroFilterFactoryBean unorderedFactory() {
        ShiroFilterFactoryBean factory = new ShiroFilterFactoryBean();
        Map<String, String> chains = new HashMap<>();
        chains.put("/hash-only/**", "anon");
        factory.setFilterChainDefinitionMap(chains);
        return factory;
    }

    void uncommittedLinkedMap() {
        LinkedHashMap<String, String> chains = new LinkedHashMap<>();
        chains.put("/uncommitted/**", "anon");
    }
}

@RestController
class FlatShiroController {
    @GetMapping("/public/open")
    void publicOpen() {}

    @GetMapping("/session/open")
    void sessionOpen() {}

    @GetMapping("/fallback/open")
    void fallbackOpen() {}

    @GetMapping("/role/open")
    void roleOpen() {}

    @GetMapping("/perm/open")
    void permOpen() {}

    @GetMapping("/admin/open")
    void adminOpen() {}

    @GetMapping("/conflict/open")
    void conflictOpen() {}

    @GetMapping("/late-public/open")
    void latePublicStillUsesFallback() {}

    @GetMapping("/hash-only/open")
    void hashMapDoesNotOverrideFallback() {}

    @GetMapping("/uncommitted/open")
    void uncommittedDoesNotOverrideFallback() {}
}

@RestController
@RequestMapping("/test/user")
class PrefixedShiroController {
    @PostMapping("/save")
    void save() {}
}
