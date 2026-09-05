package fixture.spring;

import javax.annotation.security.RolesAllowed;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnExpression;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.SecurityRules;

class FixtureCondition {}

public class SecuritySemanticsFixture {
    @fixture.customsecurity.PermitAll
    public void customPermitAll() {}

    @fixture.customsecurity.RolesAllowed("ROLE_ADMIN")
    public void customRolesAllowed() {}

    @RolesAllowed("ROLE_USER")
    public void userRole() {}

    @RolesAllowed("ROLE_ADMIN")
    public void adminRole() {}

    @RolesAllowed("SUPERADMIN")
    public void substringAdminRole() {}

    @RolesAllowed({"ROLE_ADMIN", "ROLE_USER"})
    public void mixedAdminRole() {}

    @PreAuthorize("hasRole('ADMIN')")
    public void exactAdminExpression() {}

    @PreAuthorize("hasAuthority('ROLE_ADMIN')")
    public void exactAdminAuthority() {}

    @PreAuthorize("hasRole('SUPERADMIN')")
    public void substringAdminExpression() {}

    @PreAuthorize("hasRole('USER')")
    public void userRoleExpression() {}

    @ConditionalOnBean(String.class)
    public void conditionalBean() {}

    @ConditionalOnClass(String.class)
    public void conditionalClass() {}

    @ConditionalOnExpression("${fixture.enabled:false}")
    public void conditionalExpression() {}

    @Conditional(FixtureCondition.class)
    public void conditionalGeneric() {}

    @ConditionalOnProperty(prefix = "feature", name = "enabled", havingValue = "true")
    public void prefixedProperty() {}

    @ConditionalOnProperty(prefix = "feature.", name = "enabled", havingValue = "true")
    public void dottedPrefixedProperty() {}

    @ConditionalOnProperty(
        prefix = "feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    public void matchIfMissingProperty() {}

    @Profile("!prod")
    public void negatedProfile() {}

    @Profile("prod")
    public void simpleProfile() {}

    @Profile("prod & cloud")
    public void conjunctionProfile() {}

    @Profile("prod|cloud")
    public void disjunctionProfile() {}

    @Profile({"prod", "cloud"})
    public void multipleProfiles() {}

    public void configure(SecurityRules rules) {
        rules.requestMatchers("/api/**").authenticated();
        rules.requestMatchers("/api/admin/**").hasRole("ADMIN");
        rules.requestMatchers("/api/user/**").hasRole("USER");
    }
}
