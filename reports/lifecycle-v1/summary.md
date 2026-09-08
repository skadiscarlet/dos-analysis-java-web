# Resource Lifecycle v1 固定输入评价

- 人工 IR 回归：24 例，12 组成对语义。
- 真实源码端到端：本报告不重复计入；由 CodeQL fixture 验收单独报告。
- 历史资料：29 条仅建 metadata manifest，0 条进入生命周期指标分母。
- legacy / 外部文献基线：`N/A`，本地没有可按同一输入清单运行的等价实现。
- LLM：`off`，调用 0，费用不可适用。
- 评价过程峰值 Python 分配内存：553970 bytes。

| 模式 | 完成 | unknown | 期望匹配 | 运行时 ms |
| --- | ---: | ---: | ---: | ---: |
| `full` | 24 | 9 | 24 | 32.682 |
| `without_identity` | 24 | 21 | 10 | 34.094 |
| `without_cross_event` | 24 | 12 | 18 | 30.371 |
| `without_scope` | 24 | 19 | 8 | 34.753 |
| `without_exit_coverage` | 24 | 14 | 16 | 29.865 |
| `without_invariants` | 24 | 11 | 21 | 33.059 |

完整模式的期望来自性质定义，不由当前实现输出反向生成。消融删除信息后只允许保持原状态或保守退化为 `unknown`。
本评价只检查声明的 lifecycle dimension、scope 和 assumptions，不能证明服务可用性、实际资源耗尽或动态漏洞。
