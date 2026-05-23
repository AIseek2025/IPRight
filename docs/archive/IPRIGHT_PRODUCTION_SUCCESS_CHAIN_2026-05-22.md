# IPRight 生产成功链路复盘（2026-05-22）

## 1. 文档目的

本文件用于沉淀 2026-05-22 这一轮真实生产修复中，从 `build 44` 失败一路收口到 `build 46` 端到端成功的完整链路，供后续继续迭代、线上救火、回归排查时直接参考。

这不是抽象总结，而是基于真实生产证据整理出的可复放路径。

## 2. 最终结果

- 成功 build：`46 / 47865577-21d3-4d6f-914a-65f8bc60b98e`
- 任务：`82263982-2493-476a-a6e9-9345c1d7fbf3`
- 最终状态：`task_completed`
- 关键时间线：
  - `2026-05-22T15:23:18Z` `build` 完成
  - `2026-05-22T15:23:41Z` `verify_run` 完成
  - `2026-05-22T15:26:30Z` `capture` 完成，`10/10` 截图成功
  - `2026-05-22T15:27:38Z` `compose_manual` 完成
  - `2026-05-22T15:27:46Z` `compose_code_book` 完成
  - `2026-05-22T15:27:47Z` `publish` 完成并进入 `task_completed`
- 终态清单：
  - `invalid_core_paths = null`
  - `invalid_module_paths = null`

对应时间线证据可见本地观测快照 `tmp_ipright_timeline_tail.txt`。

## 3. 成功链路总览

```text
build 44
-> 失败域前移到 WorkflowPage.tsx
-> 提取最新 invalid preview
-> 补 WorkflowPage 新负例
-> build 45
-> WorkflowPage 打穿，失败域回到 Dashboard.tsx
-> 提取 Dashboard 新 blue-shell preview
-> 补 Dashboard 新负例
-> build 46
-> core_invalid_retry 打穿
-> module_invalid_retry 全部补齐
-> verify_run 通过
-> capture 10/10
-> compose_manual 完成
-> compose_code_book 完成
-> publish 完成
-> task_completed
```

## 4. 分阶段复盘

### 4.1 build 44 的真实失败域

`build 44 / b580d7c8-f28f-4648-92b7-739d3d5ca143` 最终失败于：

- `frontend/src/pages/WorkflowPage.tsx`

真实线上 preview 为：

```tsx
import { APP_PROFILE } from '../generated/appProfile';
const WorkflowPage = () => {
  return (
    <div style={{ padding: 24 }}>
      <div style={{ marginBottom: 16, fontSize: 14, color: '#888' }}>
        {APP_PROFILE.product_name}
      </div>
      <h1 style={{ fontSize: 24, margin: '0 0 24px 0' }}>候选人管理</h1>
```

这个失败形态说明：

- 模型已经不再输出早期的重型 hooks 页面
- 但仍会在 `module_invalid_retry` 中退化成“产品名 + 历史标题 + 通用白页壳”
- 原有约束覆盖了蓝色轻壳与 `React.FC/useState`，但还没逐字命中这次的 `const WorkflowPage = () =>` + `padding: 24` + `APP_PROFILE.product_name` 顶部条

### 4.2 针对 WorkflowPage 的修复动作

本轮将最新负例下沉到三层：

1. `workers/stages/build_support.py`
   - `validation_hints` 中新增：
     - `const WorkflowPage = () =>`
     - `<div style={{ padding: 24 }}>`
     - 先显示 `APP_PROFILE.product_name`
     - H1 写成“候选人管理”

2. `backend/app/services/llm/__init__.py`
   - `WorkflowPage.tsx` 专项 prompt / retry prompt 中新增同款逐字负例

3. 测试
   - `backend/tests/test_llm.py`
   - `backend/tests/test_workers.py`
   - 新增对上述新坏形态的 prompt 与 hint 回归

### 4.3 build 45 的结果

`build 45 / 587940b2-f6bb-4c86-ba61-a4658b0a0885` 的关键变化是：

- `page:WorkflowPage` 首轮批次直接补齐
- `WorkflowPage` 不再成为终态失败域
- 新失败域回到：
  - `frontend/src/pages/Dashboard.tsx`

说明 WorkflowPage 新负例收口有效。

### 4.4 build 45 的 Dashboard 新失败形态

`build 45` 的最新 `invalid_core_preview` 为：

```tsx
import { APP_PROFILE } from '../generated/appProfile';
import { Card, Statistic } from 'antd';

export default function Dashboard() {
  const metrics = APP_PROFILE.dashboard_metrics || [];
  return (
    <div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>
      <h1 style={{ marginBottom: 24 }}>{APP_PROFILE.product_name}</h1>
```

这个失败形态说明：

- 旧的 `Typography / fallbackMetrics / columns / recentActivities` 已被连续收口
- 模型又退化成更短的新首页轻壳
- 关键问题不再是组件体量，而是：
  - `const metrics = APP_PROFILE.dashboard_metrics || []`
  - `#f3f6fb` 蓝灰背景壳
  - `APP_PROFILE.product_name` 直接充当 H1

### 4.5 针对 Dashboard blue-shell 的修复动作

本轮继续下沉到三层：

1. `workers/stages/build_support.py`
   - Dashboard validator 新增拒绝：
     - `const metrics = APP_PROFILE.dashboard_metrics || []`
     - `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`
   - Dashboard retry hints 新增：
     - 不允许把 `APP_PROFILE.product_name` 当作首页主标题
     - H1 必须是中文首页/工作台标题

2. `backend/app/services/llm/__init__.py`
   - Dashboard system prompt / user prompt / plaintext prompt 同步加入：
     - `const metrics = APP_PROFILE.dashboard_metrics || []`
     - 蓝灰轻壳 `<div style={{ padding: 24, background: '#f3f6fb', minHeight: '100vh' }}>`
     - 不得把 `APP_PROFILE.product_name` 直接写成 H1

3. 测试
   - `backend/tests/test_llm.py`
   - `backend/tests/test_workers.py`
   - 新增 Dashboard blue-shell 回归用例

## 5. build 46 的完整成功链路

`build 46 / 47865577-21d3-4d6f-914a-65f8bc60b98e` 的关键进展如下：

### 5.1 Build 阶段

- `core` 补齐
- `core_login` 补齐
- `core_dashboard` 补齐
- `support` 补齐
- `page:RecordsPage` 补齐
- `page:WorkflowPage` 补齐
- `page:AssetsPage` 补齐
- `page:AnalyticsPage` 补齐
- `page:StatisticsPage` 补齐
- `core_invalid_retry` 两次后补齐
- `module_invalid_retry` 多个单文件批次全部补齐
- 最终：
  - `应用代码已生成`
  - `运行清单校验通过`
  - `build 阶段完成`

### 5.2 Verify Run 阶段

- `2026-05-22T15:23:18Z` 开始
- `2026-05-22T15:23:41Z` 通过

证明：

- 前后端依赖安装、启动、健康检查均正常
- 没有新的编译失败或 token/运行时阻塞回归

### 5.3 Capture 阶段

- `2026-05-22T15:23:41Z` 开始
- `2026-05-22T15:26:30Z` 完成
- 结果：
  - 共尝试 `10` 张截图
  - 成功 `10` 张

### 5.4 Compose Manual / Code Book / Publish

- `compose_manual` 成功，说明书纳入 `10` 张截图，LLM=`deepseek-v4-flash`
- `compose_code_book` 成功
- `publish` 成功
- 最终进入 `task_completed`

## 6. 本轮修复为什么成功

这轮成功不是靠“放宽校验”，而是继续坚持以下原则：

1. 不做模板兜底
   - `App.tsx`、`Login.tsx`、`Dashboard.tsx`、模块页都必须由 LLM 真生成

2. 对线上最新 preview 逐字收口
   - 不做泛化猜测
   - 只对 manifest 暴露出来的最新坏形态动刀

3. 校验与 prompt 同步收紧
   - 只改 prompt 不够
   - 只改 validator 也不够
   - 必须 `validator + hints + prompt + tests` 四层同步

4. 单文件回补保持收敛
   - `core_invalid_retry`
   - `module_invalid_retry`
   - 都维持单文件批次，避免再次回到 JSON 截断大批次

5. 用真实生产证据驱动
   - 主要证据源：
     - `timeline`
     - `app_codegen_report.json`
     - `worker journal`
   - 不依赖本地想象坏形态

## 7. 后续继续沿用的操作套路

后续若再次出现同类失败，建议继续按以下步骤执行：

1. 先拉生产权威证据
   - `timeline`
   - `app_codegen_report.json`
   - `worker log`

2. 精确确认失败域
   - 先区分 `core_invalid_retry` 还是 `module_invalid_retry`
   - 再提取唯一最新 preview

3. 只修最新坏形态
   - 不同时大改多个已稳定页面
   - 优先保住已被打穿的页面链路

4. 修复四件套
   - `workers/stages/build_support.py`
   - `backend/app/services/llm/__init__.py`
   - `backend/tests/test_llm.py`
   - `backend/tests/test_workers.py`

5. 本地最小验证后再热更新
   - 只跑针对性 pytest
   - diagnostics 为空再部署

6. 生产重试后持续 live 追
   - 直到明确进入下一个失败域
   - 或真正穿过 `verify_run / capture / compose_manual / publish`

## 8. 本轮新增可复用经验

- `WorkflowPage.tsx` 不仅会退化成蓝色轻壳，也会退化成：
  - `const WorkflowPage = () =>`
  - `<div style={{ padding: 24 }}>`
  - 顶部 `APP_PROFILE.product_name`
  - H1=`候选人管理`
- `Dashboard.tsx` 不仅会退化成 `Typography` / `fallbackMetrics` / `columns` / `recentActivities`，还会继续缩成：
  - `const metrics = APP_PROFILE.dashboard_metrics || []`
  - `#f3f6fb` 蓝灰背景壳
  - 把 `APP_PROFILE.product_name` 直接写成 H1
- 当 `core_invalid_retry` 与 `module_invalid_retry` 都被打穿后，当前最佳主链依旧是：
  - `verify_run -> capture -> compose_manual -> compose_code_book -> publish`

## 9. 相关代码与文档入口

- 运行时校验与回补提示：
  - `workers/stages/build_support.py`
- LLM prompt 主入口：
  - `backend/app/services/llm/__init__.py`
- Prompt 回归测试：
  - `backend/tests/test_llm.py`
- Worker/validator 回归测试：
  - `backend/tests/test_workers.py`
- 最佳流程基线：
  - `docs/IPRIGHT_OPTIMAL_RUNTIME_PIPELINE.md`

## 10. 一句话结论

2026-05-22 这轮的关键成功点是：

- 先用 `WorkflowPage` 最新白页壳负例把失败域从模块页打回 Dashboard
- 再用 Dashboard 最新 blue-shell 负例把 `core_invalid_retry` 打穿
- 最终让生产任务首次稳定通过 `build + verify_run + capture + compose_manual + compose_code_book + publish` 全链路
