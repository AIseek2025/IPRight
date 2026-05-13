# IPRight 近期修复总结报告

## 1. 报告范围

本报告用于总结最近几天围绕 `task_id=0a01c533-15d7-4fc4-a7cb-1381333c73f1` 所进行的连续排障、代码修复、ECS 部署、截图链路修复、说明书导出修复与最终交付核验工作。

本报告覆盖以下内容：

- 遇到的主要问题
- 每个问题的定位依据与解决方案
- 最终形成的长期规则
- 本地终端与 ECS 远端的高频操作命令
- 本次多轮修复中的注意事项和踩坑记录
- 当前最终产物与验收结论

## 2. 最终结论

截至本报告生成时，最新有效成功构建为：

- `build 51`
- 任务：`0a01c533-15d7-4fc4-a7cb-1381333c73f1`
- 最终截图数量：`10`
- 全局“使用提示”已删除
- 模块页面不再统一退化为重复的“综合业务模块”
- 登录页右侧空白已修复
- 中文方框字、竖排标题、异常比例问题已修复

最新成功导出目录：

- `/opt/ipright/shared/workspace/tasks/0a01c533-15d7-4fc4-a7cb-1381333c73f1/builds/17b20345-8c17-4ad8-8152-f38a158a4233/exports`

本地已下载的最新文件：

- `tmp/upgraded_docs/software_manual_build51.docx`
- `tmp/upgraded_docs/source_code_book_build51.docx`
- `tmp/upgraded_docs/application_form_build51.docx`
- `tmp/upgraded_docs/system_architecture_build51.png`

## 3. 问题总览

### 3.1 代码生成链问题

先后遇到过以下问题：

- `App code generation failed: unknown error`
- `LLM JSON parse error`
- `empty response body`
- `finish_reason=length`
- `content_len=0`
- `reasoning_tokens` 吃满导致正文为空

### 3.2 构建与依赖问题

先后出现过：

- `name 'prd_dir' is not defined`
- 前端缺包：`axios`、`antd`、`@ant-design/icons`、`dayjs`
- 后端缺包：`PyJWT`
- 前端缺图表依赖：`echarts`、`echarts-for-react`
- `Text file busy`，由模板复制 `node_modules` 导致

### 3.3 运行验证问题

先后出现过：

- `/health` 返回 `404` 却被误判健康
- `verify_run` 依赖安装失败仅 warning、不阻断
- 后端真实异常被吞掉，看不到 traceback

### 3.4 截图与说明书问题

先后出现过：

- `No screenshots captured successfully`
- 截图文件存在但被判空白
- 双重 `BrowserRouter` 导致前端白屏
- 登录态注入键不一致导致页面未正确进入
- 中文字体变方框
- 左侧标题竖排
- 说明书截图数量不足
- 模块页面标题与正文大量重复
- 页面中出现“使用提示”无效内容
- 登录页右侧正文空白

### 3.5 操作与环境问题

先后出现过：

- `scp` 使用占位符 `<ECS_IP>` 导致主机名非法
- 在 ECS 中误用 Mac 本地路径
- `set -e` 导致 `grep` 未命中后 SSH 会话退出
- `find` 命令误写入字面量 `$`
- 新登录 shell 丢失 `TASK_ID`、`PG_DSN`
- 修复时曾引入一次 `IndentationError`，导致 `ipright-worker` 持续重启失败

## 4. 问题与解决方案明细

### 4.1 LLM 单次整包生成失败

#### 现象

- `v4-pro` 在大体量页面代码生成场景中反复出现 `finish_reason=length`
- completion token 被 reasoning 完全吃满
- 最终 `content` 为空

#### 根因

- 单次整包生成页面代码不适合当前模型输出行为
- 即使把 `max_tokens` 提高到 `12000`，仍可能全部耗在 reasoning 上

#### 解决方案

- 将代码生成从“单次整包”改为“分批/分文件”
- 对 `core` 文件与页面文件分批生成
- 后续进一步收敛为稳定模板优先、减少 LLM 覆盖面

### 4.2 前后端依赖缺失

#### 现象

- `vite build` 缺失 `axios`
- 后续缺失 `antd`、`dayjs`、`@ant-design/icons`
- 再后续缺失 `echarts`、`echarts-for-react`
- 后端出现 `ModuleNotFoundError: No module named 'jwt'`

#### 解决方案

- 在 `workers/stages/handlers.py` 增加依赖兜底逻辑
- 前端补齐常用运行时依赖
- 后端 `requirements.txt` 自动补 `PyJWT>=2.8`

### 4.3 `Text file busy`

#### 现象

- 复制模板项目时，`node_modules/@esbuild/.../esbuild` 被覆盖
- 构建阶段抛出 `shutil.Error`

#### 根因

- `shutil.copytree(..., dirs_exist_ok=True)` 连运行时目录一起复制

#### 解决方案

- 在模板复制阶段忽略以下目录：
  - `node_modules`
  - `dist`
  - `.vite`
  - `__pycache__`
  - `*.pyc`

### 4.4 健康检查误判

#### 现象

- 后端 `/health` 返回 `404`
- `health_report.json` 却仍显示 `ok=true`

#### 解决方案

- 后端健康检查改为必须 `200 <= status_code < 300`
- 前端保留 `200-399`

### 4.5 运行错误不可见

#### 现象

- `verify_run` 失败，但日志中没有真实 traceback

#### 解决方案

- 给运行时服务增加日志落盘
- 将前后端日志写入：
  - `workspace/artifacts/runtime_logs/frontend.log`
  - `workspace/artifacts/runtime_logs/backend.log`
- 同时将 `launch_log` 写入 `health_report.json`

### 4.6 白屏与空白截图

#### 现象

- `Screenshot ... appears blank after retries`
- 截图文件存在，但内容实为白屏

#### 根因

- `main.tsx` 已有 `BrowserRouter`
- 生成的 `App.tsx` 又套一层 `BrowserRouter`
- 登录态 localStorage 键名不统一

#### 解决方案

- 不再让 LLM 覆盖稳定 `App.tsx`
- 登录态注入统一写入：
  - `ipright_demo_auth`
  - `token`
  - `user`

### 4.7 中文方框字、竖排与比例异常

#### 解决方案

- 调整截图视口到宽屏桌面尺寸
- 强制中文字体回退链
- 固定横排样式
- 加宽左侧导航区域
- 去掉 `full_page` 风格的超高截图倾向

### 4.8 说明书截图数量不足

#### 解决方案

- 在 `project_profile.py` 中新增最少截图场景补齐逻辑
- 不足 `10` 张时，自动补“筛选结果”类场景

### 4.9 模块页面内容重复、“使用提示”无效

#### 现象

- 左侧多个标题重复
- 右侧正文大段相同
- 所有模块都落回同一个“综合业务模块”模板
- 每页都出现“使用提示”

#### 解决方案

- 导航优先采用模块真实标题，不再使用同质回退名
- 模块页优先采用模块真实 `title/description/rows/highlights`
- 删除全局“使用提示”
- 用“页面摘要”替代无效的说明块
- 登录页右侧增加“平台入口概览”与模块卡片

### 4.10 部署时引入缩进错误

#### 现象

- `ipright-worker` 启动失败
- `IndentationError: expected an indented block after 'for' statement`

#### 解决方案

- 本地修复缩进错误
- 再次上传 `handlers.py`
- 仅重启 worker 验证恢复

## 5. 最终形成的长期规则

以下规则已在本轮工作中明确，并要求后续全局生效：

### 5.1 截图质量规则

- 中文截图不能出现方框字
- 标题与导航必须横排
- 页面比例必须正常，不允许异常超高、超窄

### 5.2 截图数量规则

- 每次说明书必须包含 `10` 张以上截图

### 5.3 页面内容规则

- 避免左侧导航标题重复
- 避免右侧正文大段重复
- 全局删除“使用提示”区域
- 登录页/平台入口右侧正文不可空白，必须有平台介绍或模块概览

### 5.4 产品个性化规则

- 每一个软件产品的设计说明、模块结构、截图讲解、业务流程和技术特点都必须体现该产品自身的特色与个性
- 不同产品的说明书正文、模块侧重点、页面亮点和操作说明必须随关键词、行业、角色和核心模块变化而变化
- 禁止仅替换产品名称而保留大段相同正文；必须让每个产品形成可辨识的内容重心与业务表达

### 5.5 执行前阅读与范本参考规则

- 每次开始新的生成、修复或规则调整任务前，必须先尽可能完整阅读当前工作文件夹中的相关内容，先形成全面理解再执行
- 至少必须优先阅读 `IPRIGHT_CODE_AUDIT_REPORT_2026-05-08.md`、`IPRIGHT_RECENT_REPAIR_SUMMARY_2026-05-08.md`、`IPRIGHT_DOCUMENT_GENERATION_RULES.md`
- 新增的说明书范本仅用于参考章节组织、页数密度、内容展开和产品个性化表达方式，不得直接复制正文

### 5.6 文档说明与页面区块规则

- 文档说明模块中不得再出现“本次说明书基于真实运行页面自动采集……”这类固定句式
- 所有图片和页面中都不得再出现“页面摘要”区块
- 模块页正文区不得出现明显空白；即使真实数据不足，也必须提供有业务意义的兜底内容

### 5.7 源码文档与注释规则

- 代码中的注释必须从严控制，只保留理解代码所必需的说明
- 如果只是纯说明性、重复代码表意、对运行逻辑没有帮助的文字注释，必须删除
- 源码文档必须尽量上下紧凑连续排版，减少空行和大块留白
- 真实业务代码页数必须稳定达到并尽量超过 `60` 页

## 6. 关键文件变更说明

本轮核心修改文件包括：

- `workers/stages/handlers.py`
- `backend/app/services/llm/__init__.py`
- `backend/app/services/runtime/__init__.py`
- `backend/app/services/capture/__init__.py`
- `backend/app/services/project_profile.py`
- `backend/tests/test_workers.py`
- `backend/tests/test_llm.py`
- `backend/tests/test_document.py`

### 6.1 `workers/stages/handlers.py`

本轮最关键文件，承担：

- 模板项目复制
- 依赖兜底
- 分批代码生成
- 稳定模板页面生成
- 路由与导航渲染
- 登录页/首页/模块页模板渲染

### 6.2 `backend/app/services/runtime/__init__.py`

负责：

- 运行时启动前后端服务
- 落盘运行日志
- 产出 `health_report.json`
- 收紧健康检查判定

### 6.3 `backend/app/services/capture/__init__.py`

负责：

- 截图视口
- 自动登录注入
- 图片有效性判定
- 避免空白图误报

### 6.4 `backend/app/services/project_profile.py`

负责：

- 生成截图场景
- 保证截图数量至少 `10`

## 7. 本地终端常用操作命令

### 7.1 上传补丁到 ECS

```bash
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/workers/stages/handlers.py admin@8.218.209.218:/tmp/ipright-handlers.py
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/backend/tests/test_workers.py admin@8.218.209.218:/tmp/ipright-test_workers.py
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/backend/app/services/capture/__init__.py admin@8.218.209.218:/tmp/ipright-capture-init.py
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/backend/app/services/project_profile.py admin@8.218.209.218:/tmp/ipright-project_profile.py
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/backend/app/services/llm/__init__.py admin@8.218.209.218:/tmp/ipright-llm-init.py
```

### 7.2 下载最终产物到本地

```bash
mkdir -p /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/upgraded_docs

scp admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/0a01c533-15d7-4fc4-a7cb-1381333c73f1/builds/17b20345-8c17-4ad8-8152-f38a158a4233/exports/software_manual.docx /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/upgraded_docs/software_manual_build51.docx
scp admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/0a01c533-15d7-4fc4-a7cb-1381333c73f1/builds/17b20345-8c17-4ad8-8152-f38a158a4233/exports/source_code_book.docx /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/upgraded_docs/source_code_book_build51.docx
scp admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/0a01c533-15d7-4fc4-a7cb-1381333c73f1/builds/17b20345-8c17-4ad8-8152-f38a158a4233/exports/application_form.docx /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/upgraded_docs/application_form_build51.docx
scp admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/0a01c533-15d7-4fc4-a7cb-1381333c73f1/builds/17b20345-8c17-4ad8-8152-f38a158a4233/exports/system_architecture.png /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/upgraded_docs/system_architecture_build51.png
scp "admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/0a01c533-15d7-4fc4-a7cb-1381333c73f1/artifacts/screenshots/*.png" /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/upgraded_docs/
```

### 7.3 本地查看产物

```bash
open /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/upgraded_docs/
```

## 8. ECS 远端常用操作命令

### 8.1 覆盖补丁

```bash
sudo cp -f /tmp/ipright-handlers.py /opt/ipright/workers/stages/handlers.py
sudo cp -f /tmp/ipright-test_workers.py /opt/ipright/backend/tests/test_workers.py
sudo cp -f /tmp/ipright-capture-init.py /opt/ipright/backend/app/services/capture/__init__.py
sudo cp -f /tmp/ipright-project_profile.py /opt/ipright/backend/app/services/project_profile.py
sudo cp -f /tmp/ipright-llm-init.py /opt/ipright/backend/app/services/llm/__init__.py
```

### 8.2 重启服务

```bash
sudo systemctl restart ipright-api
sudo systemctl restart ipright-worker
sleep 4
systemctl is-active ipright-api
systemctl is-active ipright-worker
```

### 8.3 初始化查询变量

```bash
set +e
TASK_ID="0a01c533-15d7-4fc4-a7cb-1381333c73f1"
PG_DSN=$(grep '^IPRIGHT_DATABASE_URL=' /opt/ipright/backend/.env.production | cut -d= -f2- | sed 's/postgresql+asyncpg:/postgresql:/')
echo "$TASK_ID"
echo "$PG_DSN"
```

### 8.4 触发重跑

```bash
curl -sS -X POST "http://127.0.0.1:18000/api/v1/tasks/$TASK_ID/retry" \
  -H 'Content-Type: application/json' \
  -d '{}'
```

### 8.5 查看 build 列表

```bash
psql "$PG_DSN" -c "
select id, build_no, status, current_stage, failure_reason, started_at, finished_at
from task_builds
where task_id = '$TASK_ID'
order by build_no desc
limit 5;
"
```

### 8.6 查看单个 build 阶段

```bash
psql "$PG_DSN" -c "
select b.build_no, s.stage_name, s.status, s.failure_reason, s.started_at, s.finished_at
from task_builds b
left join build_stage_runs s on s.build_id = b.id
where b.task_id = '$TASK_ID'
  and b.build_no = 51
order by s.started_at asc nulls last;
"
```

### 8.7 查看 worker 日志

```bash
journalctl -u ipright-worker -n 260 --no-pager | grep -E "$TASK_ID|Running stage|capture|compose_manual|compose_code_book|publish|failed|succeeded|Task orchestrate_task" || true
```

### 8.8 查看截图与 manifest

```bash
cat "/opt/ipright/shared/workspace/tasks/$TASK_ID/artifacts/screenshot_manifest.json"
find "/opt/ipright/shared/workspace/tasks/$TASK_ID/artifacts/screenshots" -maxdepth 1 -type f -print | sort
```

### 8.9 查看说明书内嵌图片数

```bash
python - <<PY
from zipfile import ZipFile
from pathlib import Path
import re

task_id = "0a01c533-15d7-4fc4-a7cb-1381333c73f1"
build_id = "17b20345-8c17-4ad8-8152-f38a158a4233"
p = Path(f"/opt/ipright/shared/workspace/tasks/{task_id}/builds/{build_id}/exports/software_manual.docx")
print("exists =", p.exists(), "size =", p.stat().st_size if p.exists() else None)
with ZipFile(p) as z:
    xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
print("picture_nodes =", xml.count("<pic:pic"))
print("caption_count =", xml.count("图: "))
caps = re.findall(r"图: [^<]{1,40}", xml)
print("captions =")
for c in caps:
    print(c)
PY
```

## 9. 高风险注意事项

### 9.1 不要在 ECS 里使用 Mac 本地路径

错误示例：

```bash
ls /Users/brando/...
```

### 9.2 新登录 shell 后必须重新设置变量

必须重新执行：

```bash
TASK_ID="0a01c533-15d7-4fc4-a7cb-1381333c73f1"
PG_DSN=$(grep '^IPRIGHT_DATABASE_URL=' /opt/ipright/backend/.env.production | cut -d= -f2- | sed 's/postgresql+asyncpg:/postgresql:/')
```

### 9.3 避免 `set -e` 造成 SSH 会话中断

建议统一先执行：

```bash
set +e
```

### 9.4 `find` 命令不要写字面量 `$`

错误示例：

```bash
find ".../$TASK_ID" -maxdepth 4 $ -name "*.docx"
```

正确写法：

```bash
find "/opt/ipright/shared/workspace/tasks/$TASK_ID/builds" -maxdepth 4 \( -name "*.docx" -o -name "*.zip" \) -print
```

### 9.5 不要在新 build 尚未完成时判断截图结果

因为：

- `screenshot_manifest.json` 可能还是上一轮
- `artifacts/screenshots` 可能已开始被新一轮部分覆盖
- 容易出现“manifest 和截图目录不一致”的中间态

必须等：

- `task_builds.status=completed`
- `build_stage_runs` 全部完成
- `journalctl` 出现 `publish` 和 `Task orchestrate_task ... succeeded`

再判断最终产物。

## 10. 最终验收结果

### 10.1 截图数量与质量

- 总截图数：`10`
- 说明书截图数量不足问题：已解决
- 方框字：已解决
- 竖排与异常比例：已解决
- 重复导航标题：已解决
- 重复正文问题：已解决
- “使用提示”区域：已删除
- 登录页右侧空白：已解决

### 10.2 最新截图标题

最新 `build 51` 截图标题为：

- 登录页
- 系统首页
- 策略管理
- 回测管理
- 交易监控
- 风险管理
- 策略管理筛选结果
- 回测管理筛选结果
- 交易监控筛选结果
- 风险管理筛选结果

### 10.3 结构化检查结果

最新检查结果：

- `total = 10`
- `has_tips = False`
- `has_duplicate_business = 0`

## 11. 后续建议

后续若继续迭代，建议保持以下策略：

- 继续以稳定模板优先，减少 LLM 覆盖核心前端页面
- 每次修改后优先重跑一轮完整 build，再检查截图与说明书
- 先核对截图原始 `png`，再核对 `docx`
- 所有新规则都先落测试，再上 ECS

---

报告生成位置：

- `docs/IPRIGHT_RECENT_REPAIR_SUMMARY_2026-05-08.md`
