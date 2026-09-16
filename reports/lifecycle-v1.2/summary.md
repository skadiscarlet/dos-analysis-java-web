# 资源生命周期 v1.2 验收汇总

整轮状态：**partial**。独立已有模块为 0，H4 blocked；H6 pass。

## 输入分母

- 项目混合输入：6 条，状态 `partial`；逐阶段去向见 input-ledger.csv。
- 冻结源码：同一 fixture 的 12 个检查案例，直接复用规模 1× 的同一事实，不增加独立实验。
- 规模组：1×/2×/4× 共分别 12/24/48 个方法；仅为固定结构重命名副本，不计独立项目。
- 人工 IR 回归：24 个独立模型输入，单独列入台账与 metrics；不计源码提取或独立模块。
- 项目重复引用按原始输入保留台账，资源/性质仅按唯一身份计数；公开 properties.csv 包含其全部引用对象。

## 同事实评价

完整传播匹配 10/12，unknown 5；消融匹配 12/12，unknown 9。
完整模式不匹配案例：s2-task-only, s2-field-holder。原 oracle 未修改；backend unknown 如实保留。
确定性质增益为 4 个；两项不匹配源于缺少 callee execute rejection 到 caller/wrapper 的异常 CFG 事实。
期望 unknown 的匹配不是漏洞检出。评价仅选择正式发布性质；缺失或歧义不会生成上界零。

## 验收

- H1: pass
- H2: pass
- H3: pass
- H4: blocked
- H5: pass
- H6: pass

规模、实际字节数、峰值 RSS 和迁移目录后的语义重放见 scaling.json。测试失败、错误和 skip 按测试 ID 比较，见 baseline-test-diff.json。

## 限制

未提供两个独立已有模块，本报告不作泛化结论。任务终止切面不证明任务最终调度或总内存上界。
GitHub 交付仅含紧凑报告；真实源码、数据库、分片和日志仍位于本地持久运行目录。
运行时 HEAD/dirty、报告生成时 HEAD、同内容实现 commit、查询/实现/事实 hash 和重跑命令见 run-manifest.json。
