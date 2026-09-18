# Lifecycle E2E PoC-33 goal

本轮把 RC1 resource lifecycle 结果接入 schema 2.8/tool 0.7.0 的正式 production lifecycle/conclude/certificate/report 链，并以固定 PoC-33（33 条记录、21 个规范化项目）执行离线静态验收。

验收按 G1–G6 记录：输入与 oracle 分离、正式链真实消费、21 项必要阶段完成、33/33 正确根因匹配、全部去重阳性完成复核且达到声明阈值、交付可重跑并推送核验。unknown、失败、截断和预算退出不得计作命中或完成。

边界固定为本地源码、CodeQL DB、合成回归和远程 LLM 的已授权静态分类；不启动目标服务，不执行 PoC、负载、OOM 或网络探测。
