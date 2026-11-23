# Agent Note: 恢复前核对站点并显示快照时间

Status: implemented

## Problem

同一台服务器有两个手工部署的站点时，空目录里的配置可以指向另一站。恢复脚本会按默认项目名检查归属，Compose 却从环境文件读取实际项目名。演练结束时也可能把结果写到默认站点。

## Decision

从已有后端或 Compose 解析结果确定项目，按同一个名字检查和执行。恢复前打印目录、项目、配置网址和快照时间。演练只往已识别的后端写结果。

## Alternatives considered

只补确认文案无法保护无人值守的恢复。

## Consequences

站点已移除时需要显式给出 Compose 文件。独立演练找不到本站后端时只能从终端看结果。
