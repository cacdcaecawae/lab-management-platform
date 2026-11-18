# Agent Note: 组会 PATCH 新建子记录保留必填校验

Status: implemented

## Problem

Issue #4：父级 PATCH 的 partial 标记使新议程与新行动项跳过必填检查，遗漏成员会触发数据库异常，遗漏文字会写入空内容。

## Decision

议程每次全量替换，因此每条议程始终要求汇报人和主题；无 id 的行动项属于新增，要求负责人和内容。已有 id 的行动项保留局部更新语义。父级 PATCH、成员范围验证和数据库事务不变。

用户于 2026-11-18 授权“继续审查，确定的，可以优雅的修复但是只能先pr”，允许自主选择稳妥修复；仅草稿 PR，不合并部署。

## Alternatives considered

将父级 PATCH 改为完整更新会破坏只改标题等现有请求；捕获 IntegrityError 不能拦住遗漏文字后写入空内容，也会掩盖真正数据库故障。

## Consequences

缺成员、缺文字和空对象返回字段级 400，原有子记录不变；有效新增、已有行动项局部更新和父级局部更新成功。

## Risks

当前环境不能创建 PostgreSQL socket；使用隔离 SQLite 实测校验与 ORM 控制流，不将其视作 PostgreSQL 或浏览器验证。

## Verification

11 个回归场景通过真实 DRF 视图和 SQLite ORM 执行，复用提交的测试函数：缺成员/内容/空对象六例，null/空文字四例，正常新增及旧项/父级局部更新一例。PostgreSQL socket 被执行环境拒绝，标准 pytest 数据库套件和浏览器验收未运行。

## Related decisions

检索“组会/行动项”命中[第四期功能笔记](../feature/2026-11-17-phase4-knowledge-meetings-achievements.md)，部分重叠：本修复保留其中按 id 更新、无 id 新增及完成状态不丢的约定。其他命中不涉及嵌套必填校验；无过时提案需要替代。
