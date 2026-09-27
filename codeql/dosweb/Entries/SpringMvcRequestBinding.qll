/** Shared Spring MVC request-binding classification. */

import java

predicate isSpringMvcBindingAnnotation(Annotation annotation, string name) {
  annotation.getType().hasQualifiedName("fixture.spring", name)
  or annotation.getType().hasQualifiedName(
    "org.springframework.web.bind.annotation", name
  )
}

predicate hasExplicitSpringMvcBindingAnnotation(Parameter parameter) {
  exists(Annotation annotation |
    annotation = parameter.getAnAnnotation() and
    isSpringMvcBindingAnnotation(annotation, [
      "RequestBody", "RequestParam", "PathVariable", "RequestHeader",
      "ModelAttribute"
    ])
  )
}

predicate hasExplicitSpringMvcModelAttribute(Parameter parameter) {
  exists(Annotation annotation |
    annotation = parameter.getAnAnnotation() and
    isSpringMvcBindingAnnotation(annotation, "ModelAttribute")
  )
}

predicate isSpringMvcFrameworkValueType(Type type) {
  type.(RefType).getASupertype*().hasQualifiedName(
    ["javax.servlet.http", "jakarta.servlet.http"], "HttpServletRequest"
  )
  or type.(RefType).getASupertype*().hasQualifiedName(
    ["javax.servlet", "jakarta.servlet"], "ServletResponse"
  )
  or type.(RefType).getASupertype*().hasQualifiedName(
    ["javax.servlet.http", "jakarta.servlet.http"], "HttpSession"
  )
  or type.(RefType).getASupertype*().hasQualifiedName(
    "org.springframework.validation", "BindingResult"
  )
  or type.(RefType).getASupertype*().hasQualifiedName(
    "org.springframework.ui", ["Model", "ModelMap"]
  )
  or type.(RefType).getASupertype*().hasQualifiedName(
    "java.security", "Principal"
  )
}

predicate isSpringMvcSimpleBindingType(Type type) {
  type.(RefType).hasQualifiedName("java.lang", [
    "String", "Integer", "Long", "Boolean", "Short", "Byte", "Float",
    "Double", "Character"
  ])
}

/** Spring treats an unannotated complex handler argument as a model attribute. */
predicate isImplicitSpringMvcModelAttribute(Parameter parameter) {
  parameter.getType() instanceof RefType and
  not hasExplicitSpringMvcBindingAnnotation(parameter) and
  not isSpringMvcFrameworkValueType(parameter.getType()) and
  not isSpringMvcSimpleBindingType(parameter.getType())
}

predicate isSpringMvcModelAttributeParameter(Parameter parameter) {
  hasExplicitSpringMvcModelAttribute(parameter)
  or isImplicitSpringMvcModelAttribute(parameter)
}

predicate isSpringMvcRequestBoundParameter(Parameter parameter) {
  hasExplicitSpringMvcBindingAnnotation(parameter)
  or isImplicitSpringMvcModelAttribute(parameter)
}

string springMvcRequestBindingKind(Parameter parameter) {
  isSpringMvcBindingAnnotation(parameter.getAnAnnotation(), "RequestBody") and
  result = "request_body"
  or isSpringMvcBindingAnnotation(parameter.getAnAnnotation(), "RequestParam") and
  result = "request_parameter"
  or isSpringMvcBindingAnnotation(parameter.getAnAnnotation(), "PathVariable") and
  result = "path_parameter"
  or isSpringMvcBindingAnnotation(parameter.getAnAnnotation(), "RequestHeader") and
  result = "header"
  or isSpringMvcModelAttributeParameter(parameter) and result = "model_attribute"
}
