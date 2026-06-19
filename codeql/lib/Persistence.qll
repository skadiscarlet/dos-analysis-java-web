/**
 * Persistence.qll — Long-lived storage model for persistent-resource DoS.
 *
 * A "long-term" resource DoS requires the consumed resource to OUTLIVE the
 * request and ACCUMULATE. We model three kinds of long-lived storage WITHOUT
 * relying on library type-hierarchy resolution (broken on buildless AOSP DBs):
 *   P1. static fields (process-lifetime)
 *   P2. instance fields of a service singleton (system_server-lifetime)
 *   P3. persistent file / settings writes (survive reboot)
 *
 * Matching is by source-defined declaring type + field declared-type NAME.
 */

import java

/** A type defined in system_server source. */
class ServerType extends RefType {
  ServerType() {
    this.fromSource() and
    this.getQualifiedName().matches("com.android.server.%")
  }
}

/** Field whose DECLARED TYPE NAME looks like an accumulating container. */
class ContainerField extends Field {
  ContainerField() {
    this.getType().getName().regexpMatch(
      ".*Map.*|.*List.*|.*Set.*|.*Array.*|.*Queue.*|.*Deque.*|.*Collection.*|" +
      ".*Sparse.*|.*Cache.*|.*Pool.*|.*Registry.*|.*Store.*|.*Table.*|" +
      "RemoteCallbackList.*|.*Multimap.*|.*Histogram.*"
    )
  }
}

/**
 * P2 helper: a system_server type that is effectively a process-lifetime
 * singleton — a *Service / *ManagerService / *Controller / *Store etc whose
 * single instance is held by ServiceManager for the life of system_server.
 * Its instance fields therefore live as long as the process.
 */
class ServiceSingletonType extends ServerType {
  ServiceSingletonType() {
    this.getName().regexpMatch(
      ".*Service|.*ManagerService|.*Controller|.*Manager|.*Store|.*Registry|" +
      ".*Tracker|.*Cache|.*Repository|.*Supervisor|.*Coordinator"
    )
    or
    // held in a static field somewhere (classic singleton)
    exists(Field sf | sf.isStatic() and sf.getType() = this)
  }
}

/**
 * A type that is RETAINED for the process lifetime because a long-lived holder
 * keeps an instance in a field — transitively. E.g. ContentService (singleton)
 * has `mRootNode` of type ObserverNode, so ObserverNode instances live as long
 * as the service. Containers inside such a type are therefore also long-lived.
 * (Depth-bounded to avoid blow-up; covers the common 1-2 level helper nesting.)
 */
class RetainedType extends RefType {
  RetainedType() {
    this.fromSource() and
    exists(Field holder |
      holder.getType() = this and
      (
        holder.isStatic() or
        holder.getDeclaringType() instanceof ServiceSingletonType or
        holder.getDeclaringType() instanceof RetainedTypeBase
      )
    )
  }
}

/** One-level base to bound the recursion of RetainedType. */
class RetainedTypeBase extends RefType {
  RetainedTypeBase() {
    this.fromSource() and
    exists(Field holder |
      holder.getType() = this and
      (holder.isStatic() or holder.getDeclaringType() instanceof ServiceSingletonType)
    )
  }
}

/**
 * A ContainerField that is LONG-LIVED:
 *   P1 static container field, OR
 *   P2 instance container field of a service-singleton type, OR
 *   P3 instance container field of a type RETAINED by a long-lived holder
 *      (transitive — catches ObserverNode.mObservers held via ContentService.mRootNode).
 * These accumulate for the life of the process unless explicitly evicted.
 */
class LongLivedContainer extends ContainerField {
  string persistenceKind;

  LongLivedContainer() {
    this.isStatic() and this.getDeclaringType() instanceof ServerType and
      persistenceKind = "static"
    or
    not this.isStatic() and this.getDeclaringType() instanceof ServerType and
      this.getDeclaringType() instanceof ServiceSingletonType and
      persistenceKind = "singleton_instance"
    or
    not this.isStatic() and this.getDeclaringType().fromSource() and
      not this.getDeclaringType() instanceof ServiceSingletonType and
      this.getDeclaringType() instanceof RetainedType and
      persistenceKind = "retained_instance"
  }

  string getPersistenceKind() { result = persistenceKind }
}

/**
 * P3: a call that writes to a persistent backing store (survives reboot).
 * Matched by method NAME + declaring-type NAME (no library hierarchy needed).
 */
class PersistentWriteCall extends MethodCall {
  PersistentWriteCall() {
    exists(string dt | dt = this.getMethod().getDeclaringType().getName() |
      // AtomicFile / file writers
      (this.getMethod().getName() in ["startWrite", "finishWrite", "writeBytes"] and
       dt.matches("%AtomicFile%"))
      or
      // XML/typed serializers used for *.xml state files
      (this.getMethod().getName() in ["startTag", "attribute", "attributeInt",
        "attributeLong", "attributeBoolean", "text", "endTag"] and
       dt.regexpMatch(".*XmlSerializer.*|.*TypedXmlSerializer.*"))
      or
      // Settings provider writes
      (this.getMethod().getName().matches("put%") and dt = "Settings")
    )
  }
}

// =============================================================
// Layer 1: 长生命结构特征向量 (spec §4)
// =============================================================

/** F1: 字段是 static（进程寿命）。 */
predicate feat_isStatic(ContainerField f) { f.isStatic() }

/** F2: 被服务单例类持有。 */
predicate feat_heldBySingleton(ContainerField f) {
  not f.isStatic() and f.getDeclaringType() instanceof ServiceSingletonType
}

/** F3: 经 holder 链 retained（复用 RetainedType）。 */
predicate feat_retainedViaHolder(ContainerField f) {
  not f.isStatic() and f.getDeclaringType() instanceof RetainedType
}

/** F4: 容器无任何驱逐方法（安卓版「无回收」）。 */
predicate feat_noEvictionMethod(ContainerField f) {
  not exists(Callable m | m.getDeclaringType() = f.getDeclaringType() and
    m.getName().regexpMatch("(?i).*(evict|trim|expire|prune|removeEldest|"
      + "cleanup|reap|sweep|purge|invalidate|remove|clear).*"))
}

/** F5: 落盘 → 重启存活（安卓特有，JEE 没有）。声明类型内有持久化写调用。 */
predicate feat_survivesReboot(ContainerField f) {
  exists(PersistentWriteCall pw |
    pw.getEnclosingCallable().getDeclaringType() = f.getDeclaringType())
}

/** L1 结构分: 命中的特征数（0-5），越高越可能长生命。 */
int longLivedStructScore(ContainerField f) {
  result = count(string feat |
    (feat = "static" and feat_isStatic(f)) or
    (feat = "singleton" and feat_heldBySingleton(f)) or
    (feat = "retained" and feat_retainedViaHolder(f)) or
    (feat = "noevict" and feat_noEvictionMethod(f)) or
    (feat = "reboot" and feat_survivesReboot(f)))
}

// =============================================================
// Web-specific extensions
// =============================================================

/**
 * Web-specific: Session storage containers.
 * Matches fields in session manager types that store session data.
 */
class SessionStoreContainer extends Field {
  SessionStoreContainer() {
    this.getDeclaringType().getName().matches("%SessionManager%") and
    this.getType().getName().regexpMatch(".*Map.*|.*Store.*")
  }
}

/**
 * Web-specific: ServletContext attribute map.
 * ServletContext attributes are application-scoped and live for the
 * entire application lifetime (until undeploy/restart).
 */
class ServletContextContainer extends Field {
  ServletContextContainer() {
    this.getDeclaringType().getQualifiedName().matches("%ServletContext%") and
    this.getName().matches("%attributes%")
  }
}

/**
 * Extended LongLivedContainer to include Web-specific containers.
 * Adds session stores and ServletContext attributes to the base model.
 */
class WebLongLivedContainer extends ContainerField {
  string persistenceKind;

  WebLongLivedContainer() {
    // Base case: static container fields from source
    (
      this.isStatic() and
      this.getDeclaringType().fromSource() and
      persistenceKind = "static"
    )
    or
    // Web: Session store (process-lifetime, survives across requests)
    (
      this instanceof SessionStoreContainer and
      persistenceKind = "session_store"
    )
    or
    // Web: ServletContext attributes (application-lifetime)
    (
      this instanceof ServletContextContainer and
      persistenceKind = "servlet_context"
    )
  }

  string getPersistenceKind() { result = persistenceKind }
}

// =============================================================
// Phase 3: Web lifecycle helper predicates
// =============================================================

bindingset[name]
predicate isPersistentWebStoreName(string name) {
  name.regexpMatch("(?i).*(Redis|Jdbc|Database|File|Persistent|Repository|DataSource|Disk|Store).*")
}

predicate isEvictionLikeCallable(Callable callable) {
  callable.getName().regexpMatch("(?i).*(evict|expire|invalidate|timeout|prune|purge|cleanup).*")
}

string webContainerLifespan(string containerKind, Callable enclosingCallable) {
  containerKind in [
    "session", "servlet_context", "static_container", "session_store", "persistent_store",
    "lifecycle_field_container", "framework_registry", "parser_transaction"
  ] and
  (
    containerKind = "persistent_store" and result = "RebootPersistent"
    or containerKind = "parser_transaction" and result = "ProcessLifetime"
    or containerKind != "persistent_store" and exists(MethodCall call |
      call.getEnclosingCallable() = enclosingCallable and
      isEvictionLikeCallable(call.getMethod()) and
      result = "Evicted"
    )
    or containerKind != "persistent_store" and not exists(MethodCall call |
      call.getEnclosingCallable() = enclosingCallable and
      isEvictionLikeCallable(call.getMethod())
    ) and result = "ProcessLifetime"
  )
}

// =============================================================
// Proof-carrying Web retention sink support
// =============================================================

bindingset[name]
predicate isContainerTypeName(string name) {
  name.regexpMatch(
    ".*(Map|List|Set|Collection|Queue|Deque|Registry|Store|Cache|Table|Pool|Multimap).*"
  )
}

bindingset[name]
predicate isWebLifecycleRootTypeName(string name) {
  name.regexpMatch(
    "(?i).*(Servlet|Filter|Handler|Provider|Resource|Controller|Client|Manager|Service|Container|Context|Registry).*"
  )
}

bindingset[name]
predicate isRequestLocalContainerName(string name) {
  name.regexpMatch("(?i).*(HeaderMap|Headers|Request|Response|Attachment|Builder).*")
}

bindingset[name]
predicate isParserContainerName(string name) {
  name.regexpMatch("(?i).*(Multipart|MultiPart|MIME|Mime|Part|Parser|FormData).*")
}

class LifecycleRootFact extends Element {
  RefType rootType;
  Field rootField;
  string source;
  string lifetime;
  string confidence;
  string evidence;

  LifecycleRootFact() {
    rootField.isStatic() and
    rootField.getDeclaringType().fromSource() and
    rootField.getType() = rootType and
    source = "static_field" and
    lifetime = "ProcessLifetime" and
    confidence = "high" and
    evidence = rootField.getDeclaringType().getQualifiedName() + "." + rootField.getName() and
    this = rootField
    or
    not rootField.isStatic() and
    rootField.getDeclaringType().fromSource() and
    isWebLifecycleRootTypeName(rootField.getDeclaringType().getName()) and
    rootField.getType() = rootType and
    source = "web_taxonomy" and
    lifetime = "ProcessLifetime" and
    confidence = "medium" and
    evidence = rootField.getDeclaringType().getQualifiedName() + "." + rootField.getName() and
    this = rootField
  }

  string getSource() { result = source }

  RefType getRootType() { result = rootType }

  Field getRootField() { result = rootField }

  string getLifetime() { result = lifetime }

  string getConfidence() { result = confidence }

  string getEvidence() { result = evidence }
}

class RetainedField extends Field {
  string proofSource;
  string confidence;

  RetainedField() {
    this.fromSource() and
    not isRequestLocalContainerName(this.getType().getName()) and
    (
      isContainerTypeName(this.getType().getName()) and
      this.isStatic() and
      proofSource = "static_field" and
      confidence = "high"
      or
      isContainerTypeName(this.getType().getName()) and
      not this.isStatic() and
      isWebLifecycleRootTypeName(this.getDeclaringType().getName()) and
      proofSource = "web_taxonomy" and
      confidence = "medium"
      or
      not isContainerTypeName(this.getType().getName()) and
      not this.isStatic() and
      isWebLifecycleRootTypeName(this.getDeclaringType().getName()) and
      isWebLifecycleRootTypeName(this.getType().getName()) and
      proofSource = "framework_lifecycle" and
      confidence = "medium"
    )
  }

  string getProofSource() { result = proofSource }

  string getConfidence() { result = confidence }

  string getRetentionPath() {
    result = this.getDeclaringType().getQualifiedName() + "." + this.getName()
  }
}

predicate receiverIsFieldAccess(Expr receiver, Field field) {
  exists(FieldAccess access |
    access = receiver and
    access.getField() = field
  )
}

predicate receiverIsGetterForField(Expr receiver, Field field) {
  exists(MethodCall getter, ReturnStmt ret, FieldAccess access |
    getter = receiver and
    getter.getMethod().getNumberOfParameters() = 0 and
    getter.getMethod().getName().regexpMatch("(?i)(get|bodyParts|headers|destinations|cache|container).*") and
    ret.getEnclosingCallable() = getter.getMethod() and
    access = ret.getExpr() and
    access.getField() = field
  )
}

predicate receiverFlowsFromRetainedField(Expr receiver, RetainedField field, string path, string proofKind) {
  receiverIsFieldAccess(receiver, field) and
  path = field.getRetentionPath() and
  proofKind = "retained_field_direct"
  or
  receiverIsGetterForField(receiver, field) and
  path = field.getRetentionPath() and
  proofKind = "getter_returns_retained_field"
  or
  exists(MethodCall getter |
    getter = receiver and
    receiverFlowsFromRetainedField(getter.getQualifier(), field, path, _) and
    proofKind = "retained_field_chain_depth_1"
  )
}

class ReceiverProof extends Element {
  Expr receiver;
  RetainedField retainedField;
  string retentionPath;
  string proofKind;

  ReceiverProof() {
    receiverFlowsFromRetainedField(receiver, retainedField, retentionPath, proofKind) and
    this = receiver
  }

  Expr getReceiverExpr() { result = receiver }

  Field getRetainedField() { result = retainedField }

  string getLifecycleRoot() {
    retainedField.isStatic() and result = "static_field"
    or not retainedField.isStatic() and result = "lifecycle_field"
  }

  string getRetainedObject() { result = retainedField.getRetentionPath() }

  string getRetentionPath() { result = retentionPath }

  string getProofKind() { result = proofKind }

  string getProofSource() { result = retainedField.getProofSource() }

  string getConfidence() { result = retainedField.getConfidence() }

  string getEvidence() {
    result = getProofKind() + ":" + getRetentionPath()
  }
}
