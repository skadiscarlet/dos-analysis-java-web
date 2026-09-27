/** Exact same-instance MVC field registrations; ambiguous DI stays unresolved. */
import java

module SpringMvcFieldBindings {
  /** Traverse the complete fluent instance, including calls after an
   * exclusion. An unknown matcher/setter invalidates default path semantics. */
  predicate rootedRegistrationCall(MethodCall call, MethodCall add) {
    call = add
    or exists(MethodCall previous |
      previous = call.getQualifier() and rootedRegistrationCall(previous, add)
    )
  }

  predicate registrationSemanticsKnown(MethodCall add) {
    exists(Method owner, ExprStmt statement, MethodCall tail |
      owner = add.getEnclosingCallable() and
      statement = owner.getBody().getAStmt() and statement.getExpr() = tail and
      rootedRegistrationCall(tail, add) and
      not exists(MethodCall changed |
        rootedRegistrationCall(changed, add) and changed != add and
        not (
          changed.getMethod().getDeclaringType().hasQualifiedName(
            "org.springframework.web.servlet.config.annotation", "InterceptorRegistration"
          ) and changed.getMethod().getName() = ["addPathPatterns", "excludePathPatterns", "order"]
        )
      )
    )
  }

  private predicate conditional(RefType type) {
    exists(Annotation annotation |
      annotation = type.getAnAnnotation() and
      (annotation.getType().getName() = "Profile" or
       annotation.getType().getName().matches("Conditional%") or
       annotation.getType().getName() = "Scope")
    )
  }

  private predicate classAnnotated(RefType type, string pkg, string name) {
    exists(Annotation annotation |
      annotation = type.getAnAnnotation() and annotation.getType().hasQualifiedName(pkg, name)
    )
  }

  private predicate noWrites(Field field) {
    not exists(AssignExpr assignment |
      assignment.getDest().(FieldAccess).getField() = field and
      // The extractor represents a declaration initializer as an assignment.
      // Accept that exact AST value only; a later write has a distinct source.
      not assignment.getSource() = field.getInitializer()
    )
  }

  private predicate exactAutowiredType(Field field, RefType type) {
    not exists(field.getInitializer()) and noWrites(field) and
    type = field.getType() and type instanceof Class and type.(Class).isFinal() and
    not type.(Class).isAbstract() and type.fromSource() and
    classAnnotated(type, "org.springframework.stereotype", "Component") and
    not conditional(type) and
    not exists(Field state | state.getDeclaringType() = type and not state.isStatic()) and
    exists(Annotation injected |
      injected = field.getAnAnnotation() and injected.getType().hasQualifiedName(
        "org.springframework.beans.factory.annotation", "Autowired"
      ) and not injected.getBooleanValue("required") = false and
      not exists(Annotation other | other = field.getAnAnnotation() and other != injected)
    ) and
    not exists(Method factory, Annotation bean |
      factory.fromSource() and bean = factory.getAnAnnotation() and
      bean.getType().hasQualifiedName("org.springframework.context.annotation", "Bean") and
      factory.getReturnType().(RefType).getASupertype*() = type
    ) and
    not exists(RefType factory |
      factory.fromSource() and factory.getASupertype*().hasQualifiedName(
        "org.springframework.beans.factory", "FactoryBean"
      )
    )
  }

  predicate target(MethodCall addInterceptor, RefType type) {
    exists(FieldAccess access, Field field, Method owner, ExprStmt statement |
      access = addInterceptor.getArgument(0) and field = access.getField() and
      not field.isStatic() and field.isPrivate() and
      (not exists(access.getQualifier()) or access.getQualifier() instanceof ThisAccess) and
      owner = addInterceptor.getEnclosingCallable() and owner.fromSource() and
      field.getDeclaringType() = owner.getDeclaringType() and
      owner.getName() = "addInterceptors" and owner.getNumberOfParameters() = 1 and
      owner.getDeclaringType().getASupertype*().hasQualifiedName(
        "org.springframework.web.servlet.config.annotation", "WebMvcConfigurer"
      ) and
      classAnnotated(owner.getDeclaringType(), "org.springframework.context.annotation", "Configuration") and
      not conditional(owner.getDeclaringType()) and
      not exists(Annotation a |
        a = owner.getAnAnnotation() and
        (a.getType().getName() = "Profile" or a.getType().getName().matches("Conditional%"))
      ) and
      addInterceptor.getQualifier().(VarAccess).getVariable() = owner.getParameter(0) and
      owner.getBody().getNumStmt() = 1 and statement = owner.getBody().getStmt(0) and
      addInterceptor.getParent*() = statement and
      (
        field.isFinal() and noWrites(field) and
        type = field.getInitializer().(ClassInstanceExpr).getConstructedType()
        or exactAutowiredType(field, type)
      )
    )
  }
}
