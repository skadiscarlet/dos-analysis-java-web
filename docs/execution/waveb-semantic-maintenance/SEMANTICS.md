# Wave B 修复边界

## 来源与目标

维护基线 `a5f0e7c08d05ff72083e719d4296c058fba6e5a8` 是用户本地 agent 的132项源/测试改动快照，父提交 `42a15c8de64c190be6d5adaeea403d0dc5035f9a`。本轮补丁在该快照之上；不将用户已有实现冒称本轮贡献。

## Spring Security

新增规则域只对可核验的单一 source `@Configuration @EnableWebSecurity`、`@Bean SecurityFilterChain`、直接 HttpSecurity 配置及静态 fluent chain发布完整证据。按首次匹配选择规则；继承自 AbstractRequestMatcherRegistry 的 matcher 与 AuthorizedUrl 返回 Registry 的实际接口结构均有源码测试。末尾 anyRequest 不是任意入口的全局授权事实。

多个链、条件配置、动态 matcher、受限 securityMatcher 及超出闭合方法形状的配置保持 partial。该修复不声称支持所有 Spring Security DSL、过滤器顺序或任意自定义认证。

## MVC 字段与注册对象

只解析同一配置实例的精确私有字段：不可变直接构造值，或有严格唯一性、最终类型、无实例状态、无写入与无替代工厂的受限字段注入。歧义注入、其它实例、重赋值、条件注册不产生完整排除事实。字段初始化的隐式 AssignExpr 与后续写分开处理。

必须验证整条注册对象的使用范围。PathMatcher或未知 setter（不论位于 exclusion 之前还是之后）使默认路径解释保持 partial；Registration传给未知方法、赋值/返回等逃逸也不能借用默认匹配语义。完整注册链末端须为直接顶层表达式语句。

## Lifecycle

新增的是精确局部扫描域，不是全服务器资源耗尽证明。仅允许已支持的请求来源、精确 read-all API、未重新赋值的请求、无未知调用/分支/其它分配的局部形状；wrapper构造器还要求全部源码调用点为受支持的直传调用。调用者guard不能因为进入构造器而消失。

有限流、自定义helper、分支、非请求流、请求重赋值、未识别Spring请求来源、调用者guard等均保留partial。关闭InputStream不证明物化堆字节已释放。

## 消费与缓存

同文件/行上的多个表达式可能共享旧锚点。当同一family存在相关partial和complete行，不能靠选择complete抹去缺口；当前保守处理保持partial。未来更精细程序点可减少此类合并，但本轮未伪造列号或资源身份。另一个严格绑定的独立上界仍可用于它确实反驳的维度，不能因测试要求一概禁用。

entries v21→v22，lifecycle v20→v21，conclude v9→v10；相关旧阶段与下游缓存必须失效。provider配置和生产Growth契约未放宽。

## 参考的官方接口语义

- Spring Security请求授权与首次匹配：https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- 多链、securityMatcher与顺序：https://docs.spring.io/spring-security/reference/servlet/configuration/java.html
- MVC注册自定义匹配器：https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/servlet/config/annotation/InterceptorRegistration.html

## 评价限制

真实代码提取测试来自仓库自有小型Java源码。完整生产fixture中的模型响应由本地scripted transport给出，不能当作真实provider质量或真实漏洞召回。未启动目标服务、PoC、压力负载或第三方自主发现。历史Wave B v3的5/33是既有结果；本轮未重跑新Wave B或21库评价，不得声明召回提升或33/33完成。

## 完整源码流程暴露的证明义务错误

在同源实际提取的 /wrapper-guard 上，Guard已经验证有效，assertion_1为refuted且无未解决证据。旧最终gate仍要求发现其它Guard/Bound的扫描完整，因而把独立反证压成unknown。这与“发现漏洞需要证明没有有效防护”的义务不同。

修复只接受当前refuted assertion所对应的有效Guard/Bound/同步Release决策，要求精确原因、非空candidate/evidence引用并包含在assertion中，且两侧均无未解决证据。保留原始扫描partial；不把例外用于matched/unknown。Entry、Reach、Growth、Flow与candidate-relevant gap仍独立检查。负例确认错误Entry和candidate gap不能被该例外抹除。

当前测试环境/tmp为tmpfs、不支持原生数据库克隆所需FICLONE，项目盘btrfs支持；原生端到端命令将TMPDIR设为维护worktree内目录，不更改生产资产保护。旧scripted测试transport缺当前必需的same-flow事实引用，已补已有引用；这只修复测试协议，不改生产schema/验证，不代表远程provider测试。
