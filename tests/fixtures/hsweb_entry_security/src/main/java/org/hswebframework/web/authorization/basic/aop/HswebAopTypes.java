package org.hswebframework.web.authorization.basic.aop;

interface AopMethodAuthorizeDefinitionParser {}

interface AopMethodAuthorizeDefinitionCustomizerParser {}

class DefaultAopMethodAuthorizeDefinitionParser
        implements AopMethodAuthorizeDefinitionParser {
    void setParserCustomizers(AopMethodAuthorizeDefinitionCustomizerParser[] parsers) {}
}

class AopAuthorizingController {}
