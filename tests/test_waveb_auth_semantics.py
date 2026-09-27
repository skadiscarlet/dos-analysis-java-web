"""Actual Java extraction tests of ordered, scoped Spring authorization.

Small source-defined API stubs model the DSL contract, not a running service.
No target source, credentials, remote models, or Java execution is involved.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest
from dosweb.codeql import DecodeSource, decode_bqrs_json, run_query
from dosweb.reachability.extract import bind_entry_security_rows
from dosweb.reachability.models import AuthContract, EntrySecurityFact
from dosweb.reachability.verify import derive_auth_contract_from_facts, verify_auth_contract
from tests.support.fixture_database import fixture_database
from tests.test_codeql_hsweb_entry_security import _codeql_wrapper

ROOT = Path(__file__).resolve().parents[1]
STUBS = {
    'org/springframework/context/annotation/Configuration.java': 'package org.springframework.context.annotation; public @interface Configuration {}',
    'org/springframework/context/annotation/Bean.java': 'package org.springframework.context.annotation; public @interface Bean {}',
    'org/springframework/context/annotation/Profile.java': 'package org.springframework.context.annotation; public @interface Profile { String[] value(); }',
    'org/springframework/security/config/annotation/web/configuration/EnableWebSecurity.java': 'package org.springframework.security.config.annotation.web.configuration; public @interface EnableWebSecurity {}',
    'org/springframework/security/web/SecurityFilterChain.java': 'package org.springframework.security.web; public interface SecurityFilterChain {}',
    'org/springframework/security/config/Customizer.java': 'package org.springframework.security.config; public interface Customizer<T> { void customize(T value); }',
    'org/springframework/security/config/annotation/web/configurers/Registry.java': '''package org.springframework.security.config.annotation.web.configurers;
public class Registry {
 public Registry requestMatchers(String... patterns) { return this; }
 public Registry anyRequest() { return this; }
 public Registry authenticated() { return this; }
 public Registry permitAll() { return this; }
 public Registry hasRole(String role) { return this; }
 public Registry denyAll() { return this; }
}''',
    'org/springframework/security/config/annotation/web/builders/HttpSecurity.java': '''package org.springframework.security.config.annotation.web.builders;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.configurers.Registry;
import org.springframework.security.web.SecurityFilterChain;
public class HttpSecurity {
 public HttpSecurity authorizeHttpRequests(Customizer<Registry> rules) { return this; }
 public HttpSecurity securityMatcher(String path) { return this; }
 public SecurityFilterChain build() { return null; }
}''',
    'org/springframework/web/bind/annotation/GetMapping.java': 'package org.springframework.web.bind.annotation; public @interface GetMapping { String[] value(); String[] path() default {}; }',
    'fixture/auth/Routes.java': '''package fixture.auth;
import org.springframework.web.bind.annotation.GetMapping;
public class Routes {
 @GetMapping("/open/a") public void open() {}
 @GetMapping("/private/a") public void restricted() {}
 @GetMapping("/admin/a") public void admin() {}
}''',
}


def configuration(variant: str) -> str:
    chain = 'r.requestMatchers("/open/**").permitAll().requestMatchers("/admin/**").hasRole("ADMIN").anyRequest().authenticated()'
    if variant == 'first_match':
        chain = 'r.requestMatchers("/**").authenticated().requestMatchers("/open/**").permitAll().anyRequest().authenticated()'
    if variant == 'dynamic':
        chain = 'r.requestMatchers(System.getProperty("test.pattern")).permitAll().anyRequest().authenticated()'
    prefix = 'http.securityMatcher("/limited/**");' if variant == 'scoped' else ''
    conditional = '@org.springframework.context.annotation.Profile("test")' if variant == 'conditional' else ''
    extra = '@Bean public SecurityFilterChain second(HttpSecurity http) { return http.build(); }' if variant == 'multiple' else ''
    return '''package fixture.auth;
import org.springframework.context.annotation.*;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
@Configuration @EnableWebSecurity
public class SecurityConfiguration {
 @Bean CONDITIONAL
 public SecurityFilterChain chain(HttpSecurity http) {
   PREFIX
   http.authorizeHttpRequests(r -> CHAIN);
   return http.build();
 }
 EXTRA
}'''.replace('CONDITIONAL', conditional).replace('PREFIX', prefix).replace('CHAIN', chain).replace('EXTRA', extra)


def extract_rows(tmp_path: Path, variant: str) -> list[dict[str, object]]:
    source = tmp_path / 'source'
    files = {**STUBS, 'fixture/auth/SecurityConfiguration.java': configuration(variant)}
    if variant == 'inherited':
        # Match the documented split: matcher methods inherited from the base
        # registry; terminal authorization methods return the registry.
        files.update({
            'org/springframework/security/config/annotation/web/AbstractRequestMatcherRegistry.java': """package org.springframework.security.config.annotation.web;
public abstract class AbstractRequestMatcherRegistry<C> {
 protected abstract C chain();
 public C requestMatchers(String... patterns) { return chain(); }
 public C anyRequest() { return chain(); }
}""",
            'org/springframework/security/config/annotation/web/configurers/Registry.java': """package org.springframework.security.config.annotation.web.configurers;
import org.springframework.security.config.annotation.web.AbstractRequestMatcherRegistry;
public class Registry extends AbstractRequestMatcherRegistry<AuthorizedUrl> {
 protected AuthorizedUrl chain() { return new AuthorizedUrl(this); }
}""",
            'org/springframework/security/config/annotation/web/configurers/AuthorizedUrl.java': """package org.springframework.security.config.annotation.web.configurers;
public class AuthorizedUrl {
 private final Registry registry;
 public AuthorizedUrl(Registry registry) { this.registry = registry; }
 public Registry permitAll() { return registry; }
 public Registry authenticated() { return registry; }
 public Registry hasRole(String role) { return registry; }
}""",
        })
    for name, text in files.items():
        p = source / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text + '\n', encoding='utf-8')
    database = fixture_database(str(source))
    # Override is test-only and used for the frozen-source RED comparison.
    query = Path(os.environ.get('DOSWEB_AUTH_QUERY_UNDER_TEST', str(ROOT / 'codeql/dosweb/Entries/EntrySecurity.ql')))
    result = run_query(query, database, tmp_path / 'query', codeql_binary=str(_codeql_wrapper(tmp_path)))
    rows = decode_bqrs_json('entry_security', json.loads(result.decoded_path.read_text()), DecodeSource(database.source_root, result.query_sha256))
    evidence = os.environ.get('DOSWEB_AUTH_TEST_EVIDENCE')
    if evidence:
        out = Path(evidence)
        out.mkdir(parents=True, exist_ok=True)
        (out / (variant + '.json')).write_text(json.dumps({'query_sha256': result.query_sha256, 'rows': rows}, indent=2) + '\n')
    return rows


@pytest.mark.skipif(os.environ.get('DOSWEB_RUN_CODEQL_FIXTURES') != '1' or not shutil.which('codeql') or not shutil.which('javac'), reason='Explicit self-owned Java/CodeQL fixture opt-in required')
@pytest.mark.parametrize('variant', ['simple', 'first_match', 'inherited', 'scoped', 'dynamic', 'conditional', 'multiple'])
def test_scoped_ordered_authorization_from_real_java(tmp_path: Path, variant: str) -> None:
    rows = extract_rows(tmp_path, variant)
    selected = [r for r in rows if str(r.get('coverage_note', '')).startswith('spring_security_ordered_')]
    assert selected, 'Fallback must have concrete evidence, not silently disappear'
    if variant in {'simple', 'first_match', 'inherited'}:
        complete = [r for r in selected if r['coverage_status'] == 'complete']
        expected = {'/open/a': 'unauthenticated_filter', '/private/a': 'low_privilege_filter', '/admin/a': 'privileged_filter'}
        if variant == 'first_match':
            expected = dict.fromkeys(expected, 'low_privilege_filter')
        assert {r['route_or_event']: r['value'] for r in complete} == expected
        for route, value in expected.items():
            relevant = [r for r in selected if r['route_or_event'] == route]
            assert len(relevant) == 1
            entry = {'entry_id': 'entry:fixture', 'route_or_event': route, 'handler': {'callable': relevant[0]['handler_fqn'], 'file': relevant[0]['handler_file'], 'start_line': relevant[0]['handler_start_line']}}
            facts = bind_entry_security_rows(rows, [entry])
            contract = derive_auth_contract_from_facts('entry:fixture', facts)
            assert contract is not None, 'Legacy pattern rows must not conflict with first-match evidence'
            assert contract.auth_context == {'unauthenticated_filter':'unauthenticated','low_privilege_filter':'low_privilege','privileged_filter':'privileged'}[value]
    else:
        assert all(r['coverage_status'] == 'partial' for r in selected)
        assert not [r for r in rows if r.get('kind') == 'security_filter_chain' and r.get('coverage_status') == 'complete'], 'Unsupported chain cannot leak legacy complete rows'
