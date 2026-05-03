# IPRight ECS 正式部署与运维 README

## 1. 文档目的

本文档用于记录 `IPRight` 在阿里云 ECS 上的正式部署方案、上线步骤、证书申请方式、环境检查方法、回滚方式，以及后续标准运维路径。

本文档遵循以下原则：

- 只在 `IPRight` 自己的目录、端口、Nginx 配置和 systemd 服务内操作
- 不改动服务器上其他项目已有的目录、进程、Nginx 站点和数据库
- 所有生产入口都以 `ipright.tech` 为准
- 如服务器暂未具备截图、生成 PDF、Docker 运行生成应用所需能力，必须先做预检，再决定是否安装

---

## 2. 推荐生产形态

`IPRight` 当前更适合采用“宿主机运行应用 + Docker 承载基础设施”的隔离部署方式。

推荐形态如下：

| 项 | 值 |
|---|---|
| ECS 域名 | `ipright.tech` |
| 代码目录 | `/opt/ipright` |
| 共享目录 | `/opt/ipright/shared` |
| 任务工作目录 | `/opt/ipright/shared/workspace` |
| 前端静态发布目录 | `/var/www/ipright/releases/<timestamp>` |
| 前端 current 软链 | `/var/www/ipright/current` |
| Nginx 配置 | `/etc/nginx/conf.d/ipright.conf` |
| 后端 systemd 服务 | `ipright-api.service` |
| Worker systemd 服务 | `ipright-worker.service` |
| 后端监听 | `127.0.0.1:18000` |
| PostgreSQL | `127.0.0.1:15432` |
| Redis | `127.0.0.1:16379` |
| MinIO API | `127.0.0.1:19000` |
| MinIO Console | `127.0.0.1:19001` |

说明：

- `18000` / `15432` / `16379` / `19000` / `19001` 均为 `IPRight` 独占端口，避免与其他项目默认端口冲突
- Nginx 仅暴露 `80` / `443`，后端与基础设施只监听本机回环地址
- `IPRight` 自身不建议用 `pm2`，因为当前后端与 worker 都是 Python 进程，更适合使用 `systemd`
- 若后续需要让 `IPRight` 在服务器上自动运行生成应用并截图，宿主机必须具备 Playwright 浏览器依赖

---

## 3. 为什么采用隔离部署

服务器上已有多个项目，因此上线必须满足：

1. 不复用其他项目目录
2. 不复用其他项目后端端口
3. 不覆盖其他站点 Nginx 配置
4. 不共用其他项目的 systemd 服务名
5. 不把数据库、Redis、MinIO 直接绑定到常见默认公网端口

因此本方案采用以下隔离约束：

- 代码只放 `/opt/ipright`
- 静态资源只放 `/var/www/ipright`
- Nginx 只新增 `ipright.conf`
- 服务名只使用 `ipright-api` / `ipright-worker`
- 基础设施端口全部改为本地高位端口

---

## 4. 生产前必须检查的能力

`IPRight` 不是普通静态站点，它在服务器上可能需要做：

- 后端 API 服务
- Celery 后台任务
- 文档生成
- 页面截图
- 可选 PDF 导出
- 可选 Docker 运行生成应用

因此生产机至少需要确认以下能力。

### 4.1 必须有

- `python3`、`venv`、`pip`
- `node`、`npm`
- `nginx`
- `systemd`
- `docker`
- `docker compose`
- `git`
- `rsync`
- `curl`

### 4.2 截图能力必须有

- Python 包 `playwright`
- Chromium 浏览器及其系统依赖
- 常用中文字体

### 4.3 文档导出建议有

- `libreoffice`，用于 `.docx -> .pdf`

### 4.4 基础设施必须可用

- PostgreSQL
- Redis
- MinIO

推荐方式：

- 用 `docker compose` 仅运行 `postgres` / `redis` / `minio`
- `IPRight` 主应用本身使用宿主机 `venv + systemd`

这样可以同时满足：

- 与其他项目隔离
- 后续生成应用可继续调用宿主机 Docker
- 运维路径清晰

---

## 5. 本地与 GitHub 准备

当前本地 `IPRight` 目录已经初始化为独立 Git 仓库，并已挂载远端：

```text
https://github.com/AIseek2025/IPRight
```

正式推送前，还必须确认以下两点：

1. 本地 Git 已配置提交身份 `user.name` / `user.email`
2. 当前 Mac 对 `AIseek2025/IPRight` 具备 push 权限

如果 ECS 暂时不能直接拉 GitHub，推荐沿用 AIAds 已验证过的 `git bundle` 路径：

1. 本地提交并推送 GitHub
2. 本地创建 bundle
3. 上传 bundle 到 ECS
4. ECS 从 bundle `fetch` 并 `checkout`

---

## 6. 服务器目录约定

正式部署前，在 ECS 上创建：

```bash
sudo mkdir -p /opt/ipright
sudo mkdir -p /opt/ipright/shared/workspace
sudo mkdir -p /var/www/ipright/releases
sudo mkdir -p /var/www/ipright/current
sudo chown -R <deploy_user>:<deploy_user> /opt/ipright
sudo chown -R <deploy_user>:<deploy_user> /var/www/ipright
```

其中 `<deploy_user>` 需要替换为真实部署用户。

---

## 7. 生产环境变量建议

建议在服务器上使用：

```text
/opt/ipright/backend/.env.production
```

建议内容如下：

```bash
IPRIGHT_DEBUG=false
IPRIGHT_DB_TYPE=postgresql
IPRIGHT_DATABASE_URL=postgresql+asyncpg://ipright:<db_password>@127.0.0.1:15432/ipright
IPRIGHT_DATABASE_SYNC_URL=postgresql://ipright:<db_password>@127.0.0.1:15432/ipright
IPRIGHT_REDIS_URL=redis://127.0.0.1:16379/0
IPRIGHT_CELERY_BROKER_URL=redis://127.0.0.1:16379/1
IPRIGHT_CELERY_RESULT_BACKEND=redis://127.0.0.1:16379/2
IPRIGHT_MINIO_ENDPOINT=127.0.0.1:19000
IPRIGHT_MINIO_ACCESS_KEY=<minio_access_key>
IPRIGHT_MINIO_SECRET_KEY=<minio_secret_key>
IPRIGHT_MINIO_BUCKET=ipright
IPRIGHT_MINIO_SECURE=false
IPRIGHT_WORKSPACE_ROOT=/opt/ipright/shared/workspace
DEEPSEEK_API_KEY=<deepseek_api_key>
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
LLM_FALLBACK_MODEL=deepseek-v4-flash
```

---

## 7.1 2026-05-03 真实 ECS 预检结论

已核实的真实环境：

| 项 | 结果 |
|---|---|
| ECS 公网 IP | `8.218.209.218` |
| SSH 用户 | `admin` |
| 域名解析 | `ipright.tech`、`www.ipright.tech` 均已解析到 `8.218.209.218` |
| `sudo` | `admin` 可免密执行 |
| Docker | 已安装，`Docker 26.1.3` |
| Docker Compose | 已安装，`v2.27.0` |
| Nginx | 已安装并在监听 `80/443` |
| Python | 系统默认 `python3=3.6.8`，另有 `/usr/bin/python3.11` 可用 |
| Node / npm | 已安装，`node v24.14.0`、`npm 11.9.0` |
| `certbot` | 已安装，`1.22.0` |
| `uv` | 已安装，位于 `/home/admin/.local/bin/uv` |
| Chromium / Chrome | 未安装 |
| Playwright 浏览器 | 未安装 |
| LibreOffice | 未安装 |

已确认当前服务器上存在多个项目与容器，因此 `IPRight` 必须坚持本文件中的隔离目录、隔离端口、隔离 Nginx 配置原则。

对部署的直接影响：

- 后端运行时必须显式使用 `python3.11` 或等效隔离运行时，不能依赖系统默认 `python3.6`
- 真实截图链在上线前必须补装 `playwright + chromium + 浏览器依赖`
- `.docx -> .pdf` 导出若为生产必需，则必须补装 `libreoffice`
- `18000` / `15432` / `16379` / `19000` / `19001` 当前未发现监听占用，可继续作为 `IPRight` 规划端口

---

## 7.2 2026-05-03 真实上线结果

本轮已真实完成：

1. 本地 `IPRight` 独立 Git 仓库初始化完成，并已推送到 `AIseek2025/IPRight`
2. 线上代码目录落到 `/opt/ipright`
3. 基础设施容器已启动：
   - `ipright-postgres`
   - `ipright-redis`
   - `ipright-minio`
4. 生产环境变量已落到：
   - `/opt/ipright/.deploy.env`
   - `/opt/ipright/backend/.env.production`
5. 后端与 worker 已以 systemd 方式运行：
   - `ipright-api`
   - `ipright-worker`
6. 两个服务已启用开机自启
7. Nginx 站点配置已落到 `/etc/nginx/conf.d/ipright.conf`
8. HTTPS 证书已签发成功：
   - 证书名：`ipright.tech`
   - 域名：`ipright.tech`、`www.ipright.tech`
   - 到期时间：`2026-07-31 23:00:21+00:00`
9. 公网健康检查已通过：

```bash
curl -fsSL https://ipright.tech/health
curl -fsSL https://www.ipright.tech/health
```

返回：

```json
{"status":"ok","version":"0.1.0"}
```

10. 当前线上代码提交：

```text
539fb9c
```

---

## 7.3 2026-05-03 生产截图与导出能力补齐结果

本轮已继续补齐服务器端截图与文档导出依赖，当前可视为“生产截图/文档导出能力已就绪”：

1. 已通过 `dnf` 安装 RPM 依赖：
   - `chromium-headless`
   - `libreoffice-core`
   - `libreoffice-writer`
   - `atk`
   - `at-spi2-atk`
   - `gtk3`
   - `libXcomposite`
   - `libXdamage`
   - `libXScrnSaver`

2. `LibreOffice` 的 `.docx -> .pdf` 转换已真实验证通过
   - 已在服务器上生成临时 `smoke.docx`
   - 已成功导出 `smoke.pdf`

3. `Playwright` 截图能力已真实验证通过
   - 已使用生产机 Python 虚拟环境内的 `playwright` 启动 Chromium
   - 已成功生成 `/tmp/ipright-home.png`

4. `python -m playwright install-deps chromium` 在该系统仍不适合作为主安装方式
   - 根因是阿里云当前系统不是 Playwright 官方预设的 `apt-get` 发行版
   - 正确做法是直接用 `dnf/yum` 安装对应 RPM 依赖

5. 静态发布的 `current` 仍必须保持为软链
   - 不可预先把 `/var/www/ipright/current` 建成普通目录
   - 否则会出现首页 `403` 和 `index.html` 丢失问题

6. 健康检查公网口径统一使用：

```bash
curl -fsSL https://ipright.tech/health
```

不要用 `HEAD` 方法探测该接口，因为当前后端只接受 `GET`

---

## 7.4 2026-05-03 Demo Runner 加固结果

为保证服务器或新环境上的全链路验收更稳定，`scripts/demo_runner.py` 已做如下加固：

1. 若示例前端缺少 `node_modules`，会自动执行 `npm ci`
2. 前端不再直接起开发态 `vite dev`
3. 改为先 `npm run build`，再使用 `vite preview --host 127.0.0.1 --port 3001 --strictPort`
4. 前后端启动日志会写入 `tmp/demo_output/logs/`
5. 当健康检查失败时，会打印前后端日志尾部，便于快速定位问题

本地最新实测结果：

- `scripts/demo_runner.py` 执行通过
- 截图结果：`7/7`
- 说明书导出：`software_manual.docx` 成功
- 源码文档导出：`source_code_book.docx` 成功

---

## 8. 基础设施推荐部署方式

推荐使用：

```text
deploy/docker-compose.production.yml
```

只启动：

- PostgreSQL
- Redis
- MinIO

示例：

```bash
cd /opt/ipright
docker compose -f deploy/docker-compose.production.yml up -d
docker compose -f deploy/docker-compose.production.yml ps
```

---

## 9. 后端与 Worker 部署方式

### 9.1 Python 虚拟环境

```bash
cd /opt/ipright/backend
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### 9.2 安装截图依赖

```bash
. /opt/ipright/backend/.venv/bin/activate
pip install playwright
python -m playwright install chromium
python -m playwright install-deps chromium
```

说明：

- 若 `python -m playwright install-deps chromium` 在当前系统不可用，需要按系统发行版手工补齐浏览器依赖
- 如果这一步失败，`IPRight` 将无法在生产机上完成真实截图

### 9.3 数据库迁移

```bash
cd /opt/ipright/backend
. .venv/bin/activate
set -a
. ./.env.production
set +a
alembic upgrade head
```

### 9.4 systemd 服务

推荐使用：

- `deploy/systemd/ipright-api.service`
- `deploy/systemd/ipright-worker.service`

复制到：

```bash
sudo cp deploy/systemd/ipright-api.service /etc/systemd/system/
sudo cp deploy/systemd/ipright-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ipright-api ipright-worker
sudo systemctl restart ipright-api ipright-worker
```

---

## 10. 前端部署方式

```bash
cd /opt/ipright/frontend
npm ci
npm run build

release_ts="$(date +%Y%m%d-%H%M%S)"
static_release="/var/www/ipright/releases/$release_ts"
sudo mkdir -p "$static_release"
sudo rsync -a --delete dist/ "$static_release"/
sudo ln -sfn "$static_release" /var/www/ipright/current
```

---

## 11. Nginx 与 HTTPS

### 11.1 站点配置

推荐模板：

```text
deploy/nginx/ipright.conf.example
```

核心规则：

- `/` -> `/var/www/ipright/current`
- `/api/` -> `http://127.0.0.1:18000`

### 11.2 证书申请

推荐使用 `certbot + nginx`：

```bash
sudo certbot --nginx -d ipright.tech -d www.ipright.tech
```

若当前只解析了主域名，也可先申请：

```bash
sudo certbot --nginx -d ipright.tech
```

申请前提：

- 域名 A 记录已正确解析到目标 ECS
- `80` / `443` 已在阿里云安全组与系统防火墙开放
- Nginx 已能正常响应 `ipright.tech`

自动续期检查：

```bash
systemctl status certbot.timer
sudo certbot renew --dry-run
```

---

## 12. 上线前预检

在 ECS 上执行：

```bash
bash scripts/ipright-ecs-preflight-check.sh
```

该脚本将检查：

- Python / Node / Nginx / systemd / Docker / docker compose
- `certbot`
- `libreoffice`
- Playwright
- 生产目录
- 关键端口占用

如果预检失败，不要直接上线。

---

## 13. 推荐上线路径

### 13.1 当前优先方案

1. 本地提交代码
2. 推送到 GitHub：`AIseek2025/IPRight`
3. 若 ECS 不能直接拉 GitHub，则本地创建 bundle 并上传 ECS
4. ECS 执行：
   - 基础设施启动
   - 后端依赖安装
   - Playwright 浏览器安装
   - 数据库迁移
   - 前端构建发布
   - systemd 重启
   - Nginx 检查与 reload
   - Certbot 申请证书

### 13.2 ECS 上一条链部署

```bash
cd /opt/ipright
bash scripts/ipright-ecs-full-deploy.sh
```

---

## 14. 上线后验证

### 14.1 本机验证

```bash
curl -fsSL http://127.0.0.1:18000/health
sudo systemctl status ipright-api --no-pager
sudo systemctl status ipright-worker --no-pager
```

### 14.2 公网验证

```bash
curl -I https://ipright.tech/
curl -fsSL https://ipright.tech/api/v1/health
```

### 14.3 截图能力验证

```bash
cd /opt/ipright
python3 scripts/regenerate_latest_docs.py
```

若截图链失败，重点检查：

- Playwright 是否安装
- Chromium 是否安装成功
- 服务器图形依赖是否齐全

### 14.4 Docker 能力验证

```bash
docker --version
docker compose version
docker ps
```

如果 `IPRight` 后续要在服务器上自动运行生成应用，部署用户或运行服务用户必须具备 Docker 访问权限。

---

## 15. 回滚

### 15.1 回滚代码

若 GitHub 直拉不可用，可继续使用 bundle 回滚：

```bash
git fetch /tmp/ipright-main.bundle main
git checkout -f FETCH_HEAD
```

### 15.2 回滚静态资源

```bash
ls -1 /var/www/ipright/releases
sudo ln -sfn /var/www/ipright/releases/<old_release_ts> /var/www/ipright/current
sudo nginx -t && sudo systemctl reload nginx
```

### 15.3 回滚服务

```bash
sudo systemctl restart ipright-api ipright-worker
```

---

## 16. 需要用户配合的授权项

正式部署前，我还需要你提供或配合以下信息：

1. GitHub 仓库 `AIseek2025/IPRight` 的 push 权限
2. 当前仓库提交身份使用哪个 `Git name / Git email`
3. 是否允许在 ECS 上安装：
   - `docker` / `docker compose`
   - `playwright`
   - `chromium` 依赖
   - `libreoffice`
   - `certbot`

以下信息已确认，无需重复提供：

- ECS 公网 IP：`8.218.209.218`
- SSH 用户：`admin`
- 当前 Mac 已可通过 SSH 登录 ECS
- `ipright.tech` 与 `www.ipright.tech` 已解析到当前 ECS

---

## 17. 注意事项

1. 不要复用其他项目的 Nginx 配置
2. 不要复用其他项目的 systemd 服务名
3. 不要把 PostgreSQL、Redis、MinIO 对公网暴露
4. 证书只给 `ipright.tech` 相关域名申请
5. 若服务器当前没有 Docker，先不要假设“生成应用的 Docker 运行能力”已具备
6. 若服务器当前没有 Playwright 浏览器依赖，先不要把“自动截图成功”视为生产已就绪
7. 若服务器当前没有 LibreOffice，先不要把“PDF 导出能力”视为生产已就绪
