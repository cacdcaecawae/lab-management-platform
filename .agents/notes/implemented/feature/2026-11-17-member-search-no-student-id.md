# Agent Note: 学生搜索成员时不匹配学号（原 D19）

Status: implemented

## 问题

学号（登录名）属于成员隐私，只有本人和本组 supervisor 可见（见 [角色与课题组隔离](../architecture/2026-11-16-roles-and-group-isolation.md)）。如果学生能按学号搜索成员，就能通过搜索结果试探别人的学号。

## 决策

成员搜索的字段按角色区分（`backend/accounts/member_views.py` 的 `search_fields`）：supervisor 按姓名、学号、研究方向搜索；学生只能按姓名和研究方向搜索。

## 曾考虑的替代方案

无

## 后果

- 收益：学生无法通过搜索推断学号。
- 代价：学生不能用学号找人。
