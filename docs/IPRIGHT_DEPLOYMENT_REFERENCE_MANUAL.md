# IPRight 项目部署参考手册

## 1. 文档目的

本文档用于记录 `IPRight` 项目的标准部署、复检、修复与复跑路径，作为项目工作区内的长期运维参考。

适用场景：

- 新机器首次部署
- 线上服务重装后恢复
- 任务执行失败后的快速排查
- Playwright 截图能力失效后的修复

## 2. 生产环境基线

当前项目生产约定如下：

- 域名：`https://ipright.tech`
- SSH 别名：`ipright-prod`
- 代码目录：`/opt/ipright`
- 后端目录：`/opt/ipright/backend`
- 前端目录：`/opt/ipright/frontend`
- 共享目录：`/opt/ipright/shared`
- Playwright 浏览器目录：`/opt/ipright/shared/ms-playwright`
- 工作目录：`/opt/ipright/shared/workspace`
- 静态资源目录：`/var/www/ipright`
- API 服务：`ipright-api`
- Worker 服务：`ipright-worker`
- 后端端口：`127.0.0.1:18000`
- Redis Broker：`redis://127.0.0.1:16379/1`

说明：

- `IPRight` 生产机上的 Playwright 浏览器必须固定安装到共享目录，不要依赖 `~/.cache/ms-playwright`
- `ipright-api` 与 `ipright-worker` 都应带环境变量 `PLAYWRIGHT_BROWSERS_PATH=/opt/ipright/shared/ms-playwright`

## 3. 登录与目录

本机已配置 ECS 免密别名，常用操作：

```bash
ssh ipright-prod
ssh ipright-prod 'cd /opt/ipright && git rev-parse --short HEAD'
```

进入项目：

```bash
ssh ipright-prod
cd /opt/ipright
```

## 4. 部署前检查

### 4.1 服务与运行时

服务器应具备：

- `python3.11`
- `node`
- `npm`
- `nginx`
- `docker`
- `docker compose`
- `git`
- `rsync`
- `curl`
- `systemctl`

### 4.2 文档与截图依赖

服务器应具备：

- Python 包 `playwright`
- Playwright 浏览器二进制
- Chromium 相关系统依赖
- `libreoffice`

### 4.3 一键预检

```bash
ssh ipright-prod
cd /opt/ipright
bash scripts/ipright-ecs-preflight-check.sh
```

预检通过时，至少应看到：

- `python playwright module available`
- `playwright browser executable available: /opt/ipright/shared/ms-playwright`

如果只看到 Python 包通过，而浏览器二进制缺失，则任务截图阶段仍会失败。

## 5. 标准部署步骤

### 5.1 同步代码

按项目当前发布方式，将最新代码同步到 `/opt/ipright`。

若本机已有仓库且服务器可直接取代码，可在服务器执行：

```bash
cd /opt/ipright
git status --short
git rev-parse --short HEAD
```

### 5.2 执行部署脚本

项目内标准部署脚本：

```bash
cd /opt/ipright
bash scripts/ipright-ecs-full-deploy.sh
```

该脚本会完成：

- 创建 Python venv
- 安装后端依赖
- 安装 `playwright`
- 安装 Playwright 浏览器到共享目录
- 校验浏览器二进制是否存在
- 执行数据库迁移
- 构建前端
- 发布静态资源
- 重启 `ipright-api` 与 `ipright-worker`

## 6. Playwright 截图能力修复

### 6.1 常见故障现象

如果时间线或 worker 日志出现类似报错：

```text
BrowserType.launch: Executable doesn't exist at .../ms-playwright/.../chrome-headless-shell
```

说明：

- `playwright` Python 包已安装
- 但对应浏览器二进制不存在，或服务仍指向错误的缓存目录

### 6.2 标准修复命令

```bash
ssh ipright-prod
sudo mkdir -p /opt/ipright/shared/ms-playwright
cd /opt/ipright/backend
export PLAYWRIGHT_BROWSERS_PATH=/opt/ipright/shared/ms-playwright
. .venv/bin/activate
python -m playwright install chromium
sudo systemctl daemon-reload
sudo systemctl restart ipright-api ipright-worker
```

### 6.3 修复后验证

先看 systemd 环境变量：

```bash
sudo systemctl show ipright-worker --property=Environment --no-pager
sudo systemctl show ipright-api --property=Environment --no-pager
```

应包含：

```text
PLAYWRIGHT_BROWSERS_PATH=/opt/ipright/shared/ms-playwright
```

再执行预检：

```bash
cd /opt/ipright
bash scripts/ipright-ecs-preflight-check.sh
```

最后做浏览器烟测：

```bash
cd /opt/ipright/backend
export PLAYWRIGHT_BROWSERS_PATH=/opt/ipright/shared/ms-playwright
. .venv/bin/activate
python - <<'PY'
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-zygote",
            ],
        )
        page = await browser.new_page()
        await page.goto("https://ipright.tech", wait_until="domcontentloaded", timeout=30000)
        print(await page.title())
        await page.screenshot(path="/tmp/ipright-playwright-smoke.png", full_page=True)
        await browser.close()

asyncio.run(main())
PY
ls -lh /tmp/ipright-playwright-smoke.png
```

## 7. 服务状态检查

```bash
ssh ipright-prod
sudo systemctl status ipright-api --no-pager -l
sudo systemctl status ipright-worker --no-pager -l
```

查看最近日志：

```bash
sudo journalctl -u ipright-api -n 100 --no-pager
sudo journalctl -u ipright-worker -n 100 --no-pager
```

健康检查：

```bash
curl -fsSL http://127.0.0.1:18000/health
curl -fsSL https://ipright.tech/health
```

## 8. 失败任务复跑

### 8.1 通过 API 重试任务

```bash
curl -sS -X POST \
  https://ipright.tech/api/v1/tasks/<task_id>/retry \
  -H 'Content-Type: application/json' \
  -d '{}'
```

成功返回示例：

```json
{"code":"OK","message":"重试已触发","data":{"task_id":"<task_id>"}}
```

### 8.2 查看任务状态

```bash
curl -sS https://ipright.tech/api/v1/tasks/<task_id>/dashboard | python3 -m json.tool
curl -sS https://ipright.tech/api/v1/tasks/<task_id>/timeline | python3 -m json.tool
```

### 8.3 判断是否已越过截图故障点

查看 worker 日志中是否出现：

- `Running stage capture`
- 没有再次出现 `Executable doesn't exist at ... chrome-headless-shell`

若重试后进入 `plan`、`build`、`capture` 并继续向后推进，说明本次 Playwright 问题已修复。

## 9. 推荐发布检查清单

每次正式部署完成后建议依次确认：

1. `bash scripts/ipright-ecs-preflight-check.sh` 通过
2. `sudo systemctl status ipright-api ipright-worker` 正常
3. `curl -fsSL https://ipright.tech/health` 正常
4. Playwright 浏览器烟测通过
5. 抽样重试一个测试任务或执行一次完整链路

## 10. 本项目部署关键结论

本项目当前最重要的部署约束如下：

- 不要只安装 `playwright` Python 包，必须同时安装浏览器二进制
- 不要依赖 `admin` 用户 home 目录下的浏览器缓存
- 必须固定使用 `/opt/ipright/shared/ms-playwright`
- 预检必须覆盖“浏览器二进制是否真实存在”
- 若截图失败，优先排查 worker 的 `PLAYWRIGHT_BROWSERS_PATH` 与浏览器目录

以上原则应视为 `IPRight` 后续部署与运维的默认基线。
