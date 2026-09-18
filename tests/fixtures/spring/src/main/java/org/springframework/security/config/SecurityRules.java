package org.springframework.security.config;

public class SecurityRules {
    public SecurityRules requestMatchers(String route) { return this; }
    public SecurityRules authenticated() { return this; }
    public SecurityRules hasRole(String role) { return this; }
}
