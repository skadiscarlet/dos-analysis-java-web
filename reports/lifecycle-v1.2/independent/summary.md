# v1.2 独立模块静态源码评价

H4: **blocked**；9 条请求，3 个已有模块；实际完成分析与回放 1 个模块，来自 1 个项目。

源码来自用户允许的 PoC 所属本地仓库。仅检查所选方法的维护性资源性质，没有执行 PoC、服务或负载。
common-core最初完整模块产出8885行，触发4096行解码上限；后续限制为完整util包，排除包及文件hash留存，不修改所选方法或分析规则。原 DB 的归档字节匹配，但 live 有未归档文件，未放宽严格校验。完整主源码按原字节镜像，重新 build-mode=none 提取；不代表项目编译或外部依赖完整。XXL-JOB失败输入仍保留，新增HertzBeat common-spring后总分母为9。
无独立 oracle，不计算准确率或漏洞检出。完整/消融使用同一raw facts和正式properties；缺性质显式missing_property。

确定性质增益：0。模型未因这些输入修改，零增益也如实保留。

- xxl-job-core: 0/3 完成求解，预算退出 0，partial；full性质 {}。
- hertzbeat-common-core: 0/3 完成求解，预算退出 1，partial；full性质 {'unknown': 9}。
- hertzbeat-common-spring: 1/3 完成求解，预算退出 0，partial；full性质 {'unknown': 3}。
