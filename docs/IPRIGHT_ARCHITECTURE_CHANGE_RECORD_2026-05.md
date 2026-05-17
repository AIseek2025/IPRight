# IPRight 架构变更记录（2026-05）

## 1. 文档目的

本文档用于记录 `IPRight` 在 `2026-05` 这一轮系统级修复与重构中形成的核心架构变化、设计意图、落地结果与后续治理建议。

本文件不是一次性的阶段汇报，而是对当前已落地设计基线的正式归档。后续若继续沿着同一主线演进，应优先更新本文件，避免关键信息散落在临时纪要、聊天记录或归档报告中。

---

## 2. 本轮变更的总目标

本轮变更并非单点修 bug，而是围绕以下四个目标做系统收口：

1. 去模板化  
   不再允许不同任务稳定落到同一套固定后台壳层、同一套路页面结构和同一批通用文案。

2. 强验收  
   页面必须真实运行、真实进入目标路由、真实通过截图验收，不能靠宽松规则误判成功。

3. 强交付  
   页面、截图、说明书、导出物和下载链路必须相互对应，避免出现“页面是 A、截图像 B、说明书写 C”的断裂交付。

4. 强生产约束  
   API 鉴权、数据库生命周期、部署环境、字体资源、运维脚本与测试基线都必须显式化，不能依赖默认值或隐性约定。

---

## 3. 总体判断

本轮变更完成后，`IPRight` 的核心闭环已从“可以生成一个大致能跑的演示物”升级为“可以稳定生成、稳定验收、稳定交付、稳定运维的生产化流水线”。

当前平台的主链路可概括为：

1. 任务画像生成  
2. PRD 与代码生成要求生成  
3. 前后端与运行清单生成  
4. 启动运行与页面验证  
5. 截图采集与截图验收  
6. 软件说明书与源码文档编排  
7. 导出、打包与下载交付

这七个环节现在已被统一拉入同一套约束体系。

---

## 4. 核心架构变化

### 4.1 任务画像与页面生成从“通用模板”转向“任务 DNA 驱动”

本轮最大的架构变化，是把页面生成从“先复制示例壳层，再局部改词”调整为“围绕当前任务画像直接生成核心页面与模块页面”。

设计意图如下：

- 页面结构必须围绕当前产品主题、行业领域、角色集合、模块边界与业务对象生成。
- 不允许多个项目长期复用一套固定后台布局，只替换标题与菜单名称。
- 模块页必须体现不同 `page_variant` 的版面特征，而不是统一成一套“数据管理页”。

主要落点：

- `backend/app/services/project_profile.py`
  - 扩展了行业预设、业务实体、模块集合、角色分工、体验蓝图与产品差异化提示。
- `workers/stages/build_support.py`
  - 将代码生成要求拆分为“核心页批次 + 模块页批次”，降低统一模板吞噬差异化的概率。
- `workers/stages/generated_frontend.py`
  - 收紧本地模板边界，仅保留运行基础设施、必要外壳与字体规范，不再用模板回填业务核心页。
- `backend/app/services/llm/__init__.py`
  - 强化提示词约束，要求根据当前 `scene`、`industry_scope`、`core_entities`、`module_pages`、`experience_blueprint` 生成专属页面。

这意味着页面差异化不再依赖“运气”，而是依赖被明确表达和验证的输入约束。

### 4.2 运行期校验从“页面能打开”转向“页面内容必须匹配当前业务路由”

此前截图链路的主要风险，不在于完全截不到图，而在于错误页面被误判为成功页面。

典型风险包括：

- 登录态丢失后，业务路由落回登录页；
- 页面仍有大量文字和按钮，但主内容区其实不是目标业务内容；
- 截图验证只看粗粒度信号，导致多张图在业务上无效却被当作成功产物。

本轮变更将截图验收提升为独立架构关口。

主要落点：

- `backend/app/services/capture/__init__.py`
  - 增加路由感知的内容判定；
  - 增加主内容区抽取与期望标记校验；
  - 增加登录态恢复逻辑；
  - 明确拒绝将登录样页面当成业务页截图。
- `backend/app/services/runtime/__init__.py`
  - 增强运行期准备与校验收口。
- `backend/tests/test_workers.py`
  - 补充截图链路与页面内容判定相关回归。

这项变化的意义在于：

- 平台不再只检查“有没有截到图”；
- 平台开始检查“截到的是不是正确的业务页面”。

### 4.3 截图、说明书、导出与下载链路被统一收口为一套交付体系

此前交付链路存在几个典型断点：

- 说明书读取不到真实截图清单；
- 架构图、截图、正文内容不一致；
- 导出记录已标记完成，但磁盘文件不存在；
- 截图失败时仍写入数据库记录，前端看到空壳条目；
- bundle 下载现场打大包，线上容易超时。

本轮将这些问题统一纳入交付层治理。

主要落点：

- `workers/stages/delivery_support.py`
  - 对 `artifacts/screenshot_manifest.json` 增加回退读取；
  - 使说明书生成能加载真实截图元数据。
- `backend/app/services/document/manual.py`
  - 让说明书正文围绕当前产品画像、模块和角色生成，不再是泛化空话堆砌；
  - 统一文本清洗与字体表现。
- `backend/app/services/document/diagrams.py`
  - 解决系统架构图生成与中文字体问题。
- `backend/app/api/exports.py`
  - 增加导出路径安全校验；
  - 在导出记录与工件文件不一致时支持从工件层回退解析真实文件。
- `backend/app/api/tasks.py`
  - `bundle/download` 优先复用已有 ZIP，而不是每次现打整包；
  - 降低大任务目录下的打包超时风险。
- 截图记录写库逻辑
  - 已收紧为“只有真实图片工件创建成功，才写入 `screenshots` 记录”。

这意味着交付层不再是多个松散步骤，而是一条更强一致性的产物流水线。

### 4.4 API 与前端访问方式从“默认开放”转向“明确鉴权、明确豁免”

随着平台逐步生产化，匿名访问不再适合作为默认行为。

本轮的做法不是简单“给接口加 token”，而是建立分层鉴权模型：

- `backend/app/core/auth.py`
  - `/api/v1/admin/*` 使用 `IPRIGHT_ADMIN_TOKEN`
  - 其余 `/api/v1/*` 使用 `IPRIGHT_API_TOKEN`
  - SSE `/stream` 允许通过 `?token=` 传递鉴权信息
  - 公共下载链接保持免鉴权，作为预签名式交付面
- `backend/app/main.py`
  - 接入中间件、CORS、统一异常处理与 lifespan 生命周期
- `frontend/src/api/client.ts`
  - 自动附带 `Authorization` 头；
  - 为浏览器 `EventSource` 自动拼接查询参数 token。

这项变化的意义在于：

- 浏览器端、SSE、导出下载、后台管理接口都进入了明确边界；
- 测试也必须显式适配新约束，而不是依赖隐式匿名访问。

### 4.5 数据库与运行时基础设施从“默认可用”转向“显式生命周期管理”

随着异步服务、测试环境、ECS 重启与多终端执行增多，数据库 engine 生命周期问题开始放大。

本轮通过以下方式收口：

- `backend/app/core/database.py`
  - 让 engine 与当前进程、当前事件循环绑定；
  - 在 loop / pid 变化时重建 engine；
  - 对旧 engine 做同步侧安全释放。
- `backend/app/main.py`
  - 在应用生命周期中完成建表与 engine 回收。
- `deploy/docker-compose.production.yml`
  - 明确 PostgreSQL / Redis / MinIO 的生产容器边界。

这使得平台在本地测试、服务重启与生产运行中具备更稳定的底层行为。

---

## 5. 本轮新增的长期设计约束

以下约束应视为当前基线，不应在后续改动中被弱化：

1. 不允许用固定后台套板替代任务专属页面生成。  
2. 不允许用模板回填业务核心页来伪造“生成成功”。  
3. 不允许把登录态异常页、空白页或错误页当成业务截图。  
4. 不允许说明书脱离真实截图、真实模块和真实产品主题独立编写。  
5. 不允许导出状态与工件文件状态长期不一致。  
6. 不允许生产接口继续依赖匿名访问作为默认行为。  
7. 不允许测试绕过新生产约束而保留旧调用路径。

---

## 6. 代码与文档落点

本轮变更涉及以下关键区域：

### 6.1 生成与画像

- `backend/app/services/project_profile.py`
- `backend/app/services/llm/__init__.py`
- `workers/stages/build_support.py`
- `workers/stages/generated_frontend.py`

### 6.2 运行与截图

- `backend/app/services/runtime/__init__.py`
- `backend/app/services/capture/__init__.py`
- `workers/stages/handlers.py`
- `backend/tests/test_workers.py`

### 6.3 文档与交付

- `backend/app/services/document/base.py`
- `backend/app/services/document/manual.py`
- `backend/app/services/document/codebook.py`
- `backend/app/services/document/diagrams.py`
- `workers/stages/delivery_support.py`
- `backend/app/api/exports.py`
- `backend/app/api/tasks.py`

### 6.4 生产化基础设施

- `backend/app/core/auth.py`
- `backend/app/core/database.py`
- `backend/app/main.py`
- `frontend/src/api/client.ts`
- `frontend/src/pages/TaskDetail.tsx`
- `frontend/src/pages/TaskList.tsx`

### 6.5 测试与运维资产

- `backend/tests/conftest.py`
- `backend/tests/test_auth_middleware.py`
- `backend/tests/test_api_extended.py`
- `backend/tests/test_document.py`
- `backend/tests/test_llm.py`
- `backend/tests/test_workers.py`
- `deploy/docker-compose.production.yml`
- `docs/IPRIGHT_DOCUMENT_GENERATION_RULES.md`
- `docs/IPRIGHT_DEPLOYMENT_REFERENCE_MANUAL.md`
- `docs/IPRIGHT_ECS_DEPLOY_PRODUCTION_README.md`
- `scripts/regenerate_task_manual.py`
- `scripts/ipright-ecs-rerun-doc-fixes.sh`
- `assets/fonts/IPRightCJK.ttf`

---

## 7. 业务收益与工程收益

### 7.1 业务收益

- 不同任务的页面和截图开始真实体现行业与产品差异，而不是统一后台套板。
- 软件说明书更接近真实产品内容，减少交付时的违和感与人工解释成本。
- 任务页和下载链路的可用性提升，最终交付物更可控。

### 7.2 工程收益

- 生成链路的输入约束更清晰，可继续围绕画像与模块蓝图演进。
- 截图验收与交付一致性已成为可测试的工程边界。
- API 鉴权、数据库生命周期、部署说明和测试夹具形成了更明确的生产基线。
- 后续做线上回归和问题定位时，可直接围绕同一套链路排查，而不是在多个临时修补点之间跳转。

---

## 8. 仍需持续关注的问题

尽管本轮已完成大范围收口，后续仍建议重点跟踪以下方向：

1. 线上 smoke checklist  
   按“创建任务 -> 生成 -> 运行 -> 截图 -> 说明书 -> 导出 -> bundle 下载”做固定例行抽检。

2. 高价值集成测试  
   优先补“真实产物一致性”测试，而不是继续堆低价值单元测试。

3. 页面差异化质量守门  
   后续如继续扩展画像库与模块蓝图，需要评估是否引入页面结构相似度或文案相似度抽检。

4. 交付物一致性巡检  
   定期确认数据库记录、工件文件、下载接口与前端展示是否仍保持一致。

5. 部署基线治理  
   将 ECS 上的 Playwright、字体、导出与服务变量继续固化为正式发布前检查清单。

---

## 9. 后续维护建议

后续若继续沿着当前主线演进，建议遵循以下规则：

1. 凡是改变生成逻辑、截图逻辑、说明书逻辑或导出逻辑的改动，都应同步检查本文件。  
2. 凡是改变长期设计约束的改动，都应同时更新：
   - `docs/IPRIGHT_TECH_ARCHITECTURE.md`
   - `docs/IPRIGHT_DOCUMENT_GENERATION_RULES.md`
   - `docs/IPRIGHT_DEPLOYMENT_REFERENCE_MANUAL.md`
3. 阶段性复盘、验收纪要、线上事故排查记录，优先进入 `docs/archive/`；只有沉淀为长期基线的结论，才回写主文档区。  
4. 若后续出现新的系统级重构，建议按月份继续维护新的“架构变更记录”文件，避免单文件过度膨胀。  

---

## 10. 当前结论

截至本轮提交完成时，`IPRight` 已建立起一套以任务画像为生成起点、以运行验收为真实性关口、以说明书与导出为交付出口、以鉴权与部署基线为生产边界的系统化设计框架。

这套框架的价值不在于“这次修了多少个 bug”，而在于平台从此具备了继续稳定演进的主干结构。
