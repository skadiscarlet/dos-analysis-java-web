package fixture.deployment;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

public class DeploymentSecurityFixture {
    @ConditionalOnProperty(
        prefix = "captcha.image",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    public void defaultEnabled() {}

    @ConditionalOnProperty(
        prefix = "captcha.image",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
    )
    public void explicitlyGated() {}

    public void noHswebUniverse() {}
}
