# Agent Note: 处理记录的脚本和结果复用数据集（原 D10）

Status: implemented

## 问题

一条处理记录要能找到输入数据、脚本版本、参数和结果文件（第一期验收标准 4）。脚本和结果文件同样需要上传、校验、不可覆盖和权限控制。

## 决策

- 脚本和结果文件都存成数据集（`Dataset.kind` 为 `script` / `result`），复用 [文件上传与存储](./2026-11-16-file-upload-and-storage.md) 的同一套逻辑。
- `ProcessingRun` 用 `script_dataset` 引用脚本数据集，或用 `script_repo` + `script_commit` + `script_path` 引用代码仓库，或用 `method` 写明软件/方法；用 `output_dataset` 引用结果。2026-11-25 起这两个数据集随记录创建，在数据处理页直接上传（[科研记录二合一与项目内共享](../feature/2026-11-25-research-records-merge-and-project-sharing.md)）。

## 曾考虑的替代方案

- **另建文件表**：模型更专门；但要把上传、校验、不可覆盖和权限逻辑再写一遍。

## 后果

- 收益：只有一套文件逻辑和一套权限测试。
- 代价：数据集里混有脚本和结果，接口用 `GET /api/datasets/?kind=` 区分（页面上已没有单独的数据集列表）。
