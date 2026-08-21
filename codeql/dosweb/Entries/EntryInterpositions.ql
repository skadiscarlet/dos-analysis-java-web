/**
 * @name Registered servlet filter interpositions
 * @description Extracts source-defined FilterRegistrationBean interpositions. CFG ordering not proven is partial.
 * @kind table
 * @id dosweb/entry-interpositions
 */
import java

// Flat contract: "entry_file", "entry_start_line", "interposer_fqn", "interposer_file",
// "interposer_start_line", "registration_kind", "registration_fqn", "registration_file",
// "registration_start_line", "url_predicate_kind", "url_predicate_value", "order_status",
// "order_value", "action_fqn", "action_file", "action_start_line", "chain_file",
// "chain_start_line", "phase", "action_before_chain", "coverage_status", "coverage_note".

predicate sourceJavaMethod(Method e) {
  e.fromSource() and e.getLocation().getFile().getRelativePath().matches("%.java") and
  e.getLocation().getStartLine() > 0
}
predicate sourceJavaCall(MethodCall e) {
  e.getLocation().getFile().getRelativePath().matches("%.java") and e.getLocation().getStartLine() > 0
}

predicate isSpringAnnotation(Annotation annotation, string name) {
  annotation.getType().hasQualifiedName("fixture.spring", name)
  or annotation.getType().hasQualifiedName("org.springframework.stereotype", name)
  or annotation.getType().hasQualifiedName("org.springframework.web.bind.annotation", name)
}

predicate isController(Method method) {
  exists(Annotation annotation |
    annotation = method.getDeclaringType().getAnAnnotation() and
    isSpringAnnotation(annotation, ["Controller", "RestController"])
  )
}

predicate isMappingAnnotation(Annotation annotation) {
  isSpringAnnotation(annotation, [
    "RequestMapping", "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", "PatchMapping"
  ])
}

string mappingPath(Annotation annotation) {
  result = annotation.getAStringArrayValue("value") or
  result = annotation.getAStringArrayValue("path") or
  result = "" and
  not exists(string value |
    value = annotation.getAStringArrayValue("value") or value = annotation.getAStringArrayValue("path")
  )
}

string classPath(Method method) {
  exists(Annotation annotation |
    annotation = method.getDeclaringType().getAnAnnotation() and
    isSpringAnnotation(annotation, "RequestMapping") and result = mappingPath(annotation)
  )
  or result = "" and
  not exists(Annotation annotation |
    annotation = method.getDeclaringType().getAnAnnotation() and
    isSpringAnnotation(annotation, "RequestMapping") and mappingPath(annotation) != ""
  )
}

predicate springHandler(Method method, Annotation mapping, string route) {
  sourceJavaMethod(method) and isController(method) and mapping = method.getAnAnnotation() and
  isMappingAnnotation(mapping) and
  exists(string controllerPath, string methodPath |
    controllerPath = classPath(method) and methodPath = mappingPath(mapping) and
    (
      controllerPath = "" and route = methodPath
      or methodPath = "" and route = controllerPath
      or controllerPath != "" and methodPath != "" and route = controllerPath + "/" + methodPath
    )
  )
}

predicate isFilter(RefType t) {
  t.getASourceSupertype*().hasQualifiedName("fixture.servlet", "Filter") or
  t.getASourceSupertype*().hasQualifiedName("javax.servlet", "Filter") or
  t.getASourceSupertype*().hasQualifiedName("jakarta.servlet", "Filter")
}

predicate isFilterRegistrationBean(RefType t) {
  t.hasQualifiedName("fixture.servlet", "FilterRegistrationBean") or
  t.hasQualifiedName("org.springframework.boot.web.servlet", "FilterRegistrationBean") or
  t.(ParameterizedType).getGenericType().hasQualifiedName("fixture.servlet", "FilterRegistrationBean") or
  t.(ParameterizedType).getGenericType().hasQualifiedName("org.springframework.boot.web.servlet", "FilterRegistrationBean")
}

predicate staticUrl(MethodCall call, string route) {
  call.getMethod().getName() = ["addUrlPatterns", "setUrlPatterns"] and
  (
    call.getArgument(0) instanceof CompileTimeConstantExpr and
    route = call.getArgument(0).(CompileTimeConstantExpr).getStringValue()
    or exists(Field field, CompileTimeConstantExpr initializer |
      call.getArgument(0).(VarAccess).getVariable() = field and initializer = field.getInitializer() and
      route = initializer.getStringValue()
    )
  )
}

predicate staticOrder(MethodCall call, string value) {
  call.getMethod().getName() = "setOrder" and
  (
    call.getArgument(0) instanceof CompileTimeConstantExpr and value = call.getArgument(0).toString()
    or exists(Field field |
      call.getArgument(0).(VarAccess).getVariable() = field and field.getDeclaringType().hasQualifiedName("java.lang", "Integer") and
      field.getName() = "MIN_VALUE" and value = "-2147483648"
    )
    or exists(Field field |
      call.getArgument(0).(VarAccess).getVariable() = field and field.getDeclaringType().hasQualifiedName("java.lang", "Integer") and
      field.getName() = "MAX_VALUE" and value = "2147483647"
    )
  )
}

predicate orderInfo(MethodCall setFilter, string status, string value) {
  exists(MethodCall ordering |
    ordering.getQualifier().(VarAccess).getVariable() = setFilter.getQualifier().(VarAccess).getVariable() and
    sourceJavaCall(ordering) and staticOrder(ordering, value) and status = "known"
  )
  or not exists(MethodCall ordering, string staticValue |
    ordering.getQualifier().(VarAccess).getVariable() = setFilter.getQualifier().(VarAccess).getVariable() and
    sourceJavaCall(ordering) and staticOrder(ordering, staticValue)
  ) and status = "unknown" and value = "unknown"
}

predicate routeCovered(Method entry, Annotation mapping, MethodCall urls, string entryRoute, string filterRoute) {
  springHandler(entry, mapping, entryRoute) and staticUrl(urls, filterRoute) and
  (
    entryRoute = filterRoute
    or exists(string prefix | filterRoute = prefix + "/*" and entryRoute.matches(prefix + "/%"))
  )
}

predicate requestAccessor(MethodCall accessor) {
  accessor.getMethod().getName() = [
    "getInputStream", "getReader", "getRequestURI", "getParameter", "getParameterValues", "getPart", "getParts"
  ]
}

predicate directFilterAction(Method filter, MethodCall action, MethodCall chain) {
  filter.getName() = "doFilter" and isFilter(filter.getDeclaringType()) and
  action.getEnclosingCallable() = filter and chain.getEnclosingCallable() = filter and
  action.getMethod().fromSource() and action.getMethod().getName() != "doFilter" and
  chain.getMethod().getName() = "doFilter" and
  exists(Parameter request |
    request = filter.getParameter(0) and
    (
      action.getAnArgument().(VarAccess).getVariable() = request
      or exists(MethodCall accessor | accessor = action.getAnArgument() and requestAccessor(accessor))
    )
  ) and
  sourceJavaCall(action) and sourceJavaCall(chain)
}

from Method entry, Annotation mapping, string route, Method filter, MethodCall setFilter,
     MethodCall urls, MethodCall action, MethodCall chain, string url, string urlKind, string orderStatus, string orderValue, string note
where
  setFilter.getMethod().getName() = "setFilter" and isFilterRegistrationBean(setFilter.getMethod().getDeclaringType()) and
  setFilter.getArgument(0) instanceof ClassInstanceExpr and
  setFilter.getArgument(0).(ClassInstanceExpr).getConstructedType() = filter.getDeclaringType() and
  filter.getName() = "doFilter" and isFilter(filter.getDeclaringType()) and
  urls.getQualifier().(VarAccess).getVariable() = setFilter.getQualifier().(VarAccess).getVariable() and
  orderInfo(setFilter, orderStatus, orderValue) and
  (orderStatus = "known" and note = "cfg_action_before_chain_unproven" or orderStatus = "unknown" and note = "static_filter_order_unproven") and
  routeCovered(entry, mapping, urls, route, url) and
  (url.matches("%*%") and urlKind = "servlet_pattern" or not url.matches("%*%") and urlKind = "exact") and
  directFilterAction(filter, action, chain) and
  sourceJavaMethod(entry) and sourceJavaCall(setFilter) and sourceJavaCall(urls) and sourceJavaMethod(filter)
select entry.getLocation().getFile().getRelativePath() as entry_file,
       entry.getLocation().getStartLine() as entry_start_line,
       filter.getQualifiedName() as interposer_fqn,
       filter.getLocation().getFile().getRelativePath() as interposer_file,
       filter.getLocation().getStartLine() as interposer_start_line,
       "filter_registration_bean" as registration_kind,
       setFilter.getMethod().getDeclaringType().getQualifiedName() + ".setFilter" as registration_fqn,
       setFilter.getLocation().getFile().getRelativePath() as registration_file,
       setFilter.getLocation().getStartLine() as registration_start_line,
       urlKind as url_predicate_kind, url as url_predicate_value,
       orderStatus as order_status, orderValue as order_value,
       action.getMethod().getQualifiedName() as action_fqn,
       action.getLocation().getFile().getRelativePath() as action_file,
       action.getLocation().getStartLine() as action_start_line,
       chain.getLocation().getFile().getRelativePath() as chain_file,
       chain.getLocation().getStartLine() as chain_start_line,
       "unknown" as phase,
       false as action_before_chain,
       "partial" as coverage_status,
       note as coverage_note
