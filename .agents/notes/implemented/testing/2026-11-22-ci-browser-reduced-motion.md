# Agent Note: 浏览器场景里的测试 Chrome 请求"减少动态效果"

Status: implemented

## Problem

- v0.1.6 的首页有一个用 WebGL 画、一直在动的玻璃环（`frontend/src/views/home/glass.ts`）。GitHub 的运行机没有显卡，无头 Chrome 用 SwiftShader 在 CPU 上画 WebGL；在仿 CI 的容器里查过，渲染器是 `ANGLE (… SwiftShader Device (Subzero) …)`。每个场景都从首页登录；`login` 场景里输错密码的那个浏览器一直停在首页。
- 同一台机器、两组同时跑、各限 4 个 CPU（GitHub 公开仓库运行机的规格），脚本在 `backend/var/ci-sim`：

  | 场景 | GitHub 11-21（还没有首页） | 现在 | 测试 Chrome 请求减少动态效果 |
  |---|---|---|---|
  | login | 24 s | 258 s | 66 s |
  | members | 39 s | 285 s | 54 s |
  | experiments | 33 s | 222 s | 52 s |

  第三列仍比 GitHub 慢的部分，是这台仿真环境本身的开销。
- 机器上另有负载时（当时在构建镜像），`members` 失败过一次：第四个浏览器登录后，页面 20 秒没有响应（chromedriver：`Timed out receiving message from renderer: 20.000`）。
- WebGL 的 `failIfMajorPerformanceCaveat` 选项帮不上：无头 Chrome 把 SwiftShader 当作配置好的渲染器，照样给出上下文（同一容器里实测）。

## Decision

- `.claude/skills/verify-lab/scripts/browser/scenarios.py` 的 `browser()` 给 Chrome 加 `--force-prefers-reduced-motion`。页面里 `prefers-reduced-motion: reduce` 成立，玻璃环走已有的减少动态效果逻辑，只画一帧就停；页面其余部分照常。
- 前端代码不改，用户看到的不变。

## Alternatives considered

- **前端发现是软件渲染（渲染器名字含 SwiftShader、llvmpipe）就换成静态图**：没有显卡的真实用户也会受益。但要靠渲染器名字猜，各浏览器给的名字不一样，Firefox、Safari 会隐藏；真实用户的电脑一般有显卡，这次只在 CI 里看到问题。以后有人反映首页卡、风扇响，再考虑。
- **放宽超时**：能通过，但每个场景慢 4 到 5 倍，机器忙时仍会偶发失败。
- **保持不变**：同上。

## Consequences

- 自动化场景里看不到玻璃环转动。它本来就没有断言；转动、减少动态效果、Safari 内核和老电脑上的画面，2026-11-22 另在真实显卡和 WebKit 上看过（`backend/var/verify-evidence/2026-11-22-login/`、`2026-11-22-browsers/`）。
- 以后 Chrome 若去掉这个开关，场景照常能跑，只是回到现在的速度。
