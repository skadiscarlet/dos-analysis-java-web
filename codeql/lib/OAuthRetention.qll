/**
 * @name OAuthRetention
 * @description OAuth provider retained-state candidates for Web DoS analysis.
 */

import java

class OAuthRequestTokenEntry extends Method {
  OAuthRequestTokenEntry() {
    this.getName() = "postReqTokenRequest" and
    this.getDeclaringType().getQualifiedName() =
      "org.glassfish.jersey.server.oauth1.internal.RequestTokenResource"
  }
}

class OAuthProviderNewRequestTokenCall extends MethodCall {
  OAuthProviderNewRequestTokenCall() {
    this.getMethod().getName() = "newRequestToken" and
    exists(this.getArgument(0)) and
    exists(this.getArgument(1)) and
    exists(this.getArgument(2)) and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName() =
      "org.glassfish.jersey.server.oauth1.internal.RequestTokenResource"
  }
}

class OAuthRequestTokenMapPut extends MethodCall {
  OAuthRequestTokenMapPut() {
    this.getMethod().getName() = "put" and
    exists(this.getQualifier()) and
    exists(this.getArgument(0)) and
    exists(this.getArgument(1)) and
    this.getEnclosingCallable().getDeclaringType().getQualifiedName() =
      "org.glassfish.jersey.server.oauth1.DefaultOAuth1Provider" and
    this.getEnclosingCallable().getName() = "newRequestToken" and
    this.getQualifier().toString().regexpMatch(".*requestTokenByTokenString.*")
  }

  Expr getReceiverExpr() { result = this.getQualifier() }

  Expr getGrowthDriver() { result = this.getArgument(0) }

  Expr getStoredValue() { result = this.getArgument(1) }
}

predicate oauthRequestTokenFlow(
  OAuthRequestTokenEntry entry,
  OAuthProviderNewRequestTokenCall bridge,
  OAuthRequestTokenMapPut sink,
  string callPath
) {
  bridge.getEnclosingCallable() = entry and
  callPath = entry.getDeclaringType().getQualifiedName() + "." + entry.getName() +
    " -> " + bridge.getMethod().getDeclaringType().getQualifiedName() + "." +
    bridge.getMethod().getName() +
    " -> " + sink.getEnclosingCallable().getDeclaringType().getQualifiedName() + "." +
    sink.getEnclosingCallable().getName() +
    " -> " + sink.getMethod().getDeclaringType().getQualifiedName() + "." +
    sink.getMethod().getName()
}

string oauthRequestTokenDebugNotes(
  OAuthRequestTokenEntry entry,
  OAuthProviderNewRequestTokenCall bridge,
  OAuthRequestTokenMapPut sink
) {
  result = "token_resource=" + entry.getDeclaringType().getQualifiedName() +
    "; provider_call=" + bridge.getMethod().getName() +
    "; static_token_map=" + sink.getReceiverExpr().toString() +
    "; growth_driver=" + sink.getGrowthDriver().toString() +
    "; auth_condition=valid_oauth_consumer_signature"
}
