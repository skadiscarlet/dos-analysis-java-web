package fixture.shiro;

import java.util.LinkedHashMap;
import org.apache.shiro.spring.web.ShiroFilterFactoryBean;

class DynamicShiroConfiguration {
    ShiroFilterFactoryBean dynamicFactory(String pattern) {
        ShiroFilterFactoryBean factory = new ShiroFilterFactoryBean();
        LinkedHashMap<String, String> chains = new LinkedHashMap<>();
        chains.put(pattern, "anon");
        chains.put("/**", "user");
        factory.setFilterChainDefinitionMap(chains);
        return factory;
    }
}
