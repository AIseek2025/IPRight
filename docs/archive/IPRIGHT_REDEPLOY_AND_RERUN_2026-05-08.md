# IPRight 重部署与重跑步骤（2026-05-08）

## 1. 目标

本步骤用于将 2026-05-08 本地已完成的以下修复同步到线上环境，并重跑任务页面：

- 删除说明书中的“本次说明书基于真实运行页面自动采集……”文案
- 删除页面中的“页面摘要”区块
- 修复模块页正文区内容偏空的问题
- 增强说明书个性化内容与章节丰富度
- 压缩源码文档留白并提升源码文档页数

本次重点任务页面：

- `https://ipright.tech/tasks/c5f55bc8-9743-45f1-8839-ea48ace92455`

## 2. 需要同步的核心文件

- `backend/app/services/document/manual.py`
- `backend/app/services/document/base.py`
- `backend/app/services/document/codebook.py`
- `backend/app/services/project_profile.py`
- `workers/stages/handlers.py`

## 2.1 一键脚本

如需直接执行上传、覆盖、重启并触发重跑，可优先使用：

```bash
bash scripts/ipright-ecs-rerun-doc-fixes.sh admin@8.218.209.218
```

默认任务 ID 为：

- `c5f55bc8-9743-45f1-8839-ea48ace92455`

如需改任务 ID：

```bash
bash scripts/ipright-ecs-rerun-doc-fixes.sh admin@8.218.209.218 <TASK_ID>
```

如需从指定阶段重跑：

```bash
RERUN_FROM_STAGE=capturing bash scripts/ipright-ecs-rerun-doc-fixes.sh admin@8.218.209.218 <TASK_ID>
```

## 3. 本地上传命令

```bash
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/backend/app/services/document/manual.py admin@8.218.209.218:/tmp/ipright-manual.py
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/backend/app/services/document/base.py admin@8.218.209.218:/tmp/ipright-doc-base.py
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/backend/app/services/document/codebook.py admin@8.218.209.218:/tmp/ipright-codebook.py
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/backend/app/services/project_profile.py admin@8.218.209.218:/tmp/ipright-project_profile.py
scp /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/workers/stages/handlers.py admin@8.218.209.218:/tmp/ipright-handlers.py
```

## 4. ECS 覆盖补丁

```bash
sudo cp -f /tmp/ipright-manual.py /opt/ipright/backend/app/services/document/manual.py
sudo cp -f /tmp/ipright-doc-base.py /opt/ipright/backend/app/services/document/base.py
sudo cp -f /tmp/ipright-codebook.py /opt/ipright/backend/app/services/document/codebook.py
sudo cp -f /tmp/ipright-project_profile.py /opt/ipright/backend/app/services/project_profile.py
sudo cp -f /tmp/ipright-handlers.py /opt/ipright/workers/stages/handlers.py
```

## 5. 重启服务

```bash
sudo systemctl restart ipright-api
sudo systemctl restart ipright-worker
sleep 4
systemctl is-active ipright-api
systemctl is-active ipright-worker
```

若需要同时重启前端：

```bash
sudo systemctl restart ipright-frontend
sleep 3
systemctl is-active ipright-frontend
```

## 6. 初始化查询变量

```bash
set +e
TASK_ID="c5f55bc8-9743-45f1-8839-ea48ace92455"
PG_DSN=$(grep '^IPRIGHT_DATABASE_URL=' /opt/ipright/backend/.env.production | cut -d= -f2- | sed 's/postgresql+asyncpg:/postgresql:/')
echo "$TASK_ID"
echo "$PG_DSN"
```

## 7. 触发任务重跑

```bash
curl -sS -X POST "http://127.0.0.1:18000/api/v1/tasks/$TASK_ID/retry" \
  -H 'Content-Type: application/json' \
  -d '{}'
```

如需从指定阶段重跑，可改为：

```bash
curl -sS -X POST "http://127.0.0.1:18000/api/v1/tasks/$TASK_ID/retry" \
  -H 'Content-Type: application/json' \
  -d '{"from_stage":"capturing"}'
```

建议优先从头重跑一次；若仅确认文档与截图修复，也可从 `capturing` 或 `writing_manual` 开始试跑。

## 8. 查看构建状态

```bash
psql "$PG_DSN" -c "
select id, build_no, status, current_stage, failure_reason, started_at, finished_at
from task_builds
where task_id = '$TASK_ID'
order by build_no desc
limit 5;
"
```

## 9. 查看阶段执行情况

```bash
psql "$PG_DSN" -c "
select b.build_no, s.stage_name, s.status, s.failure_reason, s.started_at, s.finished_at
from task_builds b
left join build_stage_runs s on s.build_id = b.id
where b.task_id = '$TASK_ID'
order by b.build_no desc, s.started_at asc nulls last;
"
```

## 10. 查看 worker 日志

```bash
journalctl -u ipright-worker -n 260 --no-pager | grep -E "$TASK_ID|Running stage|capture|compose_manual|compose_code_book|publish|failed|succeeded|Task orchestrate_task" || true
```

## 11. 结果核验

### 11.1 截图 manifest

```bash
cat "/opt/ipright/shared/workspace/tasks/$TASK_ID/artifacts/screenshot_manifest.json"
find "/opt/ipright/shared/workspace/tasks/$TASK_ID/artifacts/screenshots" -maxdepth 1 -type f -print | sort
```

### 11.2 下载最新导出文件

```bash
LATEST_BUILD_ID=$(psql "$PG_DSN" -t -A -c "
select id
from task_builds
where task_id = '$TASK_ID'
order by build_no desc
limit 1;
")
echo "$LATEST_BUILD_ID"
```

```bash
mkdir -p /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/online_rerun_docs

scp admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/$TASK_ID/builds/$LATEST_BUILD_ID/exports/software_manual.docx /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/online_rerun_docs/
scp admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/$TASK_ID/builds/$LATEST_BUILD_ID/exports/source_code_book.docx /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/online_rerun_docs/
scp admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/$TASK_ID/builds/$LATEST_BUILD_ID/exports/application_form.docx /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/online_rerun_docs/
scp "admin@8.218.209.218:/opt/ipright/shared/workspace/tasks/$TASK_ID/artifacts/screenshots/*.png" /Users/brando/Documents/trae_projects/CodeMaster/isolated_autoruns/IPRight/tmp/online_rerun_docs/
```

### 11.3 核验要点

- 说明书中不再出现“本次说明书基于真实运行页面自动采集……”
- 模块页截图中不再出现“页面摘要”
- 模块页正文区不应出现明显空白，应可见业务列表、卡片或处理说明
- 说明书页数应不少于 `20`
- 源码文档页数应不少于 `60`
- 截图数量应不少于 `10`
- 说明书正文应体现当前产品主题与模块差异，不能只换标题

## 12. 本地验证样例

本地已生成一套样例产物，可作为重跑后对照：

- `tmp/generated_review_2026-05-08/software_manual_sample.docx`
- `tmp/generated_review_2026-05-08/source_code_book_sample.docx`
- `tmp/generated_review_2026-05-08/verification_summary.txt`

## 13. 当前本地阻塞说明

- 本地尝试执行 `docker compose up -d ...` 时，Docker Hub 镜像元数据拉取超时
- 阻塞点是外网镜像拉取，不是本轮代码修改
- 因此当前最稳妥的落地路径是将补丁同步到现有 ECS 环境并重跑任务
