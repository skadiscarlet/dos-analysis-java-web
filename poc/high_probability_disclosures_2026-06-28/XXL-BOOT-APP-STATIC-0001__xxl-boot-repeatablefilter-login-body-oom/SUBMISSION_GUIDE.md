# GitHub Issue 提交指南：XXL-BOOT-APP-STATIC-0001 + XXL-BOOT-APP-STATIC-0003

## 提交位置

目标仓库：`xuxueli/xxl-boot`

建议提交位置：

- GitHub issue: https://github.com/xuxueli/xxl-boot/issues
- 如果仓库启用了私密漏洞报告，也可优先使用：https://github.com/xuxueli/xxl-boot/security/advisories/new
- Security 页面：https://github.com/xuxueli/xxl-boot/security

## 提交方式

这份目录中的 `VULNERABILITY_REPORT.md` 已经改成中文 GitHub issue 正文，可以直接复制到 issue 里。

建议标题：

```text
[安全] 匿名 /login 请求体复制与登录失败异步日志队列可导致 JVM OOM
```

正文：

```text
复制 VULNERABILITY_REPORT.md 的全部内容。
```

## 说明

- `XXL-BOOT-APP-STATIC-0001` 和 `XXL-BOOT-APP-STATIC-0003` 已合并为同一份 issue，因为二者都属于 XXL-Boot 登录相关匿名 HTTP 面导致 JVM OOM / 服务不可用的问题。
- issue 正文不引用附件位置，也不要求上传本地附件；必要的源码证据、动态验证摘要和 OOM 日志信号已经内联到正文中。
- 原始动态日志和 JSON 证据仍保留在本地目录中，只在维护者要求私下补充时再提供。
