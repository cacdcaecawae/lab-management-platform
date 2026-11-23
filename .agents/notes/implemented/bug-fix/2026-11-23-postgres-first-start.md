# Agent Note: 等待 PostgreSQL 首次初始化完成

Status: implemented

## Problem

空卷第一次启动 PostgreSQL 时会同步数据到磁盘，再启动临时数据库建库。在本地磁盘并发写入的恢复演练中，一分钟后 Compose 已判数据库不健康。临时数据库只监听 Unix socket，原探针在它运行期间也可能误报就绪。

## Decision

生产和演练的探针通过本机 TCP 检查 PostgreSQL，允许首次初始化占用额外的启动时间；恢复演练继续设置总体超时。

## Alternatives considered

脚本中固定休眠会延迟每次正常启动。

## Consequences

首次启动失败时需等待更长时间才能报告失败。
