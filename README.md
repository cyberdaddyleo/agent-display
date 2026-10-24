# Agent 战术大屏 · v6.0

一个纯前端的 **AI 智能体调度可视化大屏**。v6.0 新增原生 WebGL 主题 FORGE 视界熔炉，以黑洞吸积子 Agent 情报、星核投影出完整产品后拆解、逐件锻造交付的流程展示智能体协作。在同一个 HTML 页面里切换 OPS、SPIDER、NEURAL、FACTORY、NEBULA、FORGE 六款主题，展示任务流、质检、交付与模拟指标。

单文件，无需构建、无需后端，双击即可打开。自 v5.0 起源码公开，采用 PolyForm Noncommercial License 1.0.0：非商业用途免费，商业用途需授权，详见文末「授权 License」。

> 页面中的任务、需求文本、需求评分、追问回答、工单、Agent 负载、业务指标、token 与成本全部是**模拟示例数据**，由内置模拟器生成，并未连接真实 agent、账单或业务接口；FORGE 的吸积数据包、星核质量、已锻零件、交付记录与吞吐也均为本地模拟。真实数据接入需要自行改造，见「配置」一节。SPIDER、NEURAL、FACTORY 的 token 成本使用示例单价：输入 ¥2 / 百万 token、缓存命中 ¥0.5 / 百万 token、输出 ¥8 / 百万 token。

## 主题

| 编号 | 主题 | 风格 | 直达 |
| --- | --- | --- | --- |
| 01 | OPS 纸面工程 | 纸面工程图 + 调度飞轮，可切粒子荧光 | `index.html#ops` |
| 02 | SPIDER 蛛网战术 | 粉框作战室 + 巡检蛛 + token 账 + 交付飞轮 | `index.html#spider` |
| 03 | NEURAL 神经星环 | 3D 神经团 + 任务脉冲 + HUD 星环 + token 账 | `index.html#neural` |
| 04 | FACTORY 机器人工厂 | 3D 机器人车间 + 子板块接力 + 总装发射 | `index.html#factory` |
| 05 | NEBULA 星核蜘蛛 | 3D 智能体星云 + 逐字审需求 + 评分派单 | `index.html#nebula` |
| 06 | FORGE 视界熔炉 | 黑洞吸积子 Agent 情报 + 星核投影出整机再拆解 + 逐件锻造交付 | `index.html#forge` |

点各主题的「主题 / 换主题」按钮打开主题面板，按 T 键依次轮换 OPS → SPIDER → NEURAL → FACTORY → NEBULA → FORGE，再回到 OPS；按 Esc 关闭面板。选择保存在 localStorage；地址中的 `#ops`、`#spider`、`#neural`、`#factory`、`#nebula` 或 `#forge` 优先于上次选择。没有有效选择记录时默认打开 SPIDER。

每款主题运行在独立的 Shadow DOM 中，样式和元素 id 互不干扰。隐藏主题暂停主动画与主要模拟刷新，减少资源占用。六款主题和主题面板使用系列水印「DEVELOPED BY @赛博老爸」。主题面板另有「07 · 下一款」占位。

## 功能一览

### 01 · OPS 纸面工程

原 v1 的调度飞轮与面板作为主题 01 保留，提供「换主题」与「全屏」按钮。

- **数据飞轮**：左侧汇聚连线与三个工作流节点，中间旋转的代码和执行记录环带，右侧外射谱线，以及齿环、扫光与质检浮层。悬停节点可查看工作流详情。
- **顶部指标**：任务、运行中智能体、工作流、产出、已匹配、待复核，以及实时时钟。
- **底部四个面板**：任务日志、粒子求解器、执行代码打字展示、12 个智能体的任务与进度。
- **纸面 / 粒子荧光**：默认跟随系统深浅色；点「粒子」按钮切到荧光绿画面，按钮变为「纸面」，再点切回。深色画面包含柔光与偶发横向故障效果。
- **粒子交互**：点击粒子面板或聚焦后按 Enter 加入涡流；ADVECT / PROJECT 切换流动模式，RERUN 重置。
- **自适应**：宽屏四列面板，宽度 ≤1100px 时两列，手机竖屏单列。

### 02 · SPIDER 蛛网战术

以 1920×1080 横屏为设计尺寸，按窗口等比缩放，推荐电脑或手机横屏观看。

- **14 张角色卡**：总调度 CHIEF、12 个 agent、巡检蛛 CRAWLER，显示当前任务、进度和台词。
- **作战室**：12 个工位与总调度台，模拟派单 → 接手 → 交接 → 质检 → 交付。交接会飞出光点，或由角色踩滑板送到下一工位；空闲 agent 优先接单，久候会去沙发。质检不通过会打回重写并触发碎纸效果。
- **巡检蛛**：在屏幕上巡逻，腿抓住事件元素四角，显示锁定框和说明；打回时亮出 REWORK LOCKED，巡逻工位时织网。
- **token 消耗墙屏**：按 agent 颜色分段堆叠，显示预算线、当前速率和 TOP BURN 前四名。
- **交付飞轮**：汇聚节点轮换展示在途较多的工作流，环带滚动任务记录与 token 账；交付推动飞轮并射出光束，打回时减速。悬停节点查看接力顺序。
- **产出与成本**：今日交付、今日 token、今日成本，以及单件 token / 成本。
- **质检台**：需求覆盖、事实核验、品牌口径、合规敏感词、重复率、交付时限逐项 PASS / DROP，展示近 30 次得分曲线及最近三条结果。
- **rules.py 面板**：模拟校验 token 上限、队列深度、通过率、周期、打回次数，以及单件 token、品牌口径、事实覆盖和重复率；它是页面展示内容，无需 Python 环境。
- **其他面板与控制**：dispatch 流程芯片、执行代码打字、任务流、12 席负载、今日进度、全屏和时钟。悬停作战室角色可查看任务、排队数、今日交付和 token。

### 03 · NEURAL 神经星环

three.js（WebGL）渲染的 3D agent 协同大屏。13 团神经元代表 CHIEF 总调度与 12 个执行智能体，另有 CRAWLER 巡检探针在各团之间飞行。角色、11 条工作流与 6 个交付渠道沿用 SPIDER 的配置内容；源码在两个挂载函数内分别定义这些配置。

- **任务脉冲**：派单、交接沿突触束飞行，打回显示红色脉冲；抵达时神经团亮起，交付光束射向外环渠道并点亮它。
- **HUD 星环**：72 块 × 6 道能量格记录 token 流水与智能体忙碌程度，包含反向充能波、超预算琥珀提示、执行记录文字带、智能体扇区与交付渠道环。神经网与标签约三分钟一圈，标签自动翻正。
- **视角与交互**：工具栏按钮或 V 键切换环绕、正视、斜看、贴近四种视角；拖动转视角、滚轮缩放；点击神经团聚焦，悬停查看详情。
- **状态与指标**：左列展示 14 个角色状态与最近交接，右列展示神经活动热力格、突触日志和巡检统计；底部展示拓扑规模、脉冲频率、交付进度、审校通过率、token、成本与帧率。
- **性能与适配**：辉光效果使用 UnrealBloom；持续低帧率时先降低清晰度，再减少粒子。画板随比例伸展，窄屏或竖屏使用只保留星环和三个核心数字的精简版。
- **背景效果**：`AMBIENT` 控制背景粒子和流星，默认全部关闭，可按需调整。

### 04 · FACTORY 机器人工厂

three.js（WebGL）渲染的整座 3D 机器人车间，以俯瞰视角展示「总工程 → 8 个子板块 → 工区接力 → 中央总装 → 发射」的模拟生产流程。

- **总工程与总装**：双11 大促战役、智能投标交付、新品发布会、品牌出海计划轮流开工，每项拆成 8 个子板块，对应火箭、机甲、航天飞机、战斗机四种载具。子板块完成后由无人机吊装并入；全部并入后倒计时、点火发射，显示 LAUNCH SUCCESS，再开下一个工程。
- **12 个工区与总调度室**：CHIEF 控制全局，检索、拆解、文案、设计、代码、测试、审校、数据、剪辑、投放、客服、归档机器人各有不同造型与专属机器。货箱沿双向传送带流转，外圈有 AGV 巡线，4 架无人机吊装，CRAWLER 沿传送带巡检。
- **进度显示**：机器人旁的卡片显示岗位、动作、进度与当前子板块；中央总工程进度条列出 8 个子板块的待派、运输、加工、返工、吊装、已并入状态。倒计时与发射横幅出现时，卡片和总工程条变淡。
- **五个底部面板**：TASK FLOW 子板块任务流、KPI 今日指标、LINE LOAD 工区负载、RADAR 车间雷达、EXEC 执行代码。指标包含总工程交付、本工程用时、子板块、审校通过率、算力与帧率，负载面板另有 OEE 环及交接曲线。
- **视角与交互**：工具栏按钮或 V 键切换俯瞰、斜看、环绕、特写；拖动转视角、滚轮缩放；点击机器人拉近工区，按 Esc 返回；悬停查看详情。
- **视觉与适配**：UnrealBloom 辉光与软阴影；持续低帧率时依次降低清晰度、关闭阴影。画面适配 16:10、1366×768 等比例；窄屏或竖屏精简为车间与总工程、子板块、今日交付三个数字。

### 05 · NEBULA 星核蜘蛛

冰蓝、白、桃粉的 3D 星云场景：CHIEF 是中央丝带星核，12 个智能体分在三条椭圆轨道上公转，CRAWLER 星云蛛在相关工区之间跳跃、爬行和读词。

- **星图与星云蛛**：三圈分别分布 3、4、5 团星云，六种形态交替排列。星云由淡光雾、尘埃和细丝组成；星云蛛有粒子头部、丝带腹部与 8 条逆解控制的腿，贴着云面移动并随星云公转。
- **模拟审需求流程**：CHIEF 收到需求后，星云蛛按工作流逐站读词；普通词可连向下一工区，模糊词标红并向 CHIEF 追问，随后补为具体要求。全部读完后回到星核，显示回执和派单效果。评分阈值为 80 分，需求、补齐文本与评分均由本地脚本模拟，并未调用模型审查真实需求。
- **信息小框**：读出的词、模糊标记、补齐要求、连线与属性标签沿弧线飞向对应底部面板，被击中面板边框闪亮。
- **六个底部面板**：CRAWL LOG 爬取日志、SECTIONS 章节、SPEC RADAR 七维需求质量、WORD HEAT 读词热力、SPEC SCORE 评分曲线与仪表盘、CRAWLER.PY 审查脚本。顶部另有当前章节、读词计数、流程步骤与帧率。
- **视角与交互**：默认跟随，工具栏按钮或 V 键切换跟随、俯瞰、斜看、环绕；拖动转视角、滚轮缩放；点击智能体星云拉近，Esc 返回；悬停星云、星核或星云蛛查看详情。
- **视觉与适配**：UnrealBloom 辉光；持续低帧率时先降清晰度，再关辉光。窄屏或竖屏显示星云与当前需求、需求评分、今日派单三个数字。

### 06 · FORGE 视界熔炉

原生 WebGL 绘制的黑洞与星核投影场景。左侧 8 个子 Agent 的情报沿彩色线束汇入黑洞，星核投影出当前工单的完整产品，再拆成代表子任务的零件，逐件锻造、合拢后交付。

- **五步流程**：吸积 → 成形（完整产品投影）→ 拆解 → 锻造 → 交付。内部状态机还处理坍缩、合拢和星核回收，完成后自动轮换下一张示例工单。
- **六种投影**：人形机器人（智能客服机器人上线）、推进器（招投标资料自动生成）、工业产线（短视频生产线提速）、园区工程地图（智慧园区建设工程）、行星减速器（企业知识库迁移）、机械臂（合同审查自动化）。每张工单有 6–8 个零件，分别对应子任务与负责 Agent。
- **情报流与派发**：彩色粒子经左侧 STATE IN 总线进入黑洞后消失，在星核中停留片刻，再带着来源 Agent 的颜色从右侧 DISPATCH OUT 总线派发，伴随光尾、余烬、总线闪光与工位到达提示。右侧线束采用负责 Agent 的颜色；完整产品投影出现时黑洞隐去，交付后的回收阶段重新出现。
- **Agent 阵列与锻造工位**：左侧显示 8 个 Agent 的模拟负载、上下文与活动柱；右侧显示零件任务、负责人、进度、当前工序及交付记录。当前工序细分为解析需求、生成方案、执行改动、交叉校验、合并入核，并展示模拟 token 吞吐、累计用量与耗时。
- **四个底部面板**：事件流、调度负载、执行代码、星核遥测。`FORGE.PY` 按阶段持续逐字输出开工与提交脚本，当前行高亮、锻造时变为琥珀色，Agent 名按各自颜色显示，写满自动滚动；它是展示内容，无需 Python 环境。遥测展示模拟吸积包数、星核质量、已锻零件与交付工单，以及吸积曲线和实际帧率。
- **视角与交互**：默认环绕，工具栏按钮或 V 键切换环绕、正视、俯瞰；拖动旋转、滚轮缩放、双击复位。点击工位卡或零件标注暂时高亮聚焦该零件，稍后自动解除，也可按 Esc 解除。
- **适配与动态效果**：以 1920×1080 为基准缩放；窄屏或竖屏自动切换精简版，保留星核、当前工单、锻造进度与今日交付。系统开启「减少动态效果」时减少流光数量、停止自动环绕与 HUD 转动、减慢模拟与零件转动，并减少部分 CSS 动画。

当前六款主题均无暂停按钮与空格键暂停；SPIDER 无倍速按钮。系统开启「减少动态效果」时，大屏仍会运行，部分 CSS 动画和故障闪烁减少；FORGE 另有上述动态效果降级。

## 快速开始

### 本地打开

直接双击 `index.html`，用支持 Shadow DOM 和 Canvas 的现代 Chrome / Edge / Safari / Firefox 打开。NEURAL、FACTORY 与 NEBULA 的 3D 画面另需 WebGL 与可访问 jsDelivr 的网络；首次切入其中任一款时加载共用的 three.js 及后处理脚本，正常加载完成后可供这三款主题复用。FORGE 同样需要 WebGL，但使用原生实现，切入时无需加载 three.js 或其他外部脚本。

也可以任选一种方式启动静态服务器：

```bash
python3 -m http.server 8000
# 或
npx serve .
```

使用 Python 命令后访问 `http://localhost:8000`；使用 `npx serve .` 时访问终端显示的地址。加上 `#ops`、`#spider`、`#neural`、`#factory`、`#nebula` 或 `#forge` 可直达主题。

### 部署到 GitHub Pages

1. 将文件推送到 GitHub 仓库。
2. 在仓库 Settings → Pages 中，将 Source 选为 `Deploy from a branch`，分支选 `main`，目录选 `/ (root)`。
3. 等待部署完成，使用 Pages 设置页提供的地址访问；在地址末尾加 `#ops`、`#spider`、`#neural`、`#factory`、`#nebula` 或 `#forge` 检查六款主题。

也可以部署到其他静态托管服务，无需安装运行时或构建项目。

### 放到大屏上

在电脑或小主机上打开页面，使用浏览器全屏功能；常见快捷键为 F11（Mac 为 Ctrl+Cmd+F）。六款主题的桌面布局均提供「全屏」按钮。推荐 1920×1080 或更高分辨率。

## 配置（换成你自己的数据）

业务与视觉配置主要位于 `index.html` 的各主题挂载函数内；按需加载的 CDN 地址及依赖列表位于页面末尾的系列外壳脚本。

| 位置 | 配置 | 内容 |
| --- | --- | --- |
| `mountOps(host, SR)` | `CONFIG` | agent 名单、任务名称、工作流、执行代码示例 |
| `mountOps(host, SR)` | `CODEBITS`、`SPIN` | 环带代码片段、飞轮转速 |
| `mountSpider(host, SR)` | `AG` | 角色名单、颜色、形状、话术、速度 |
| `mountSpider(host, SR)` | `WF`、`CH` | 工作流、接力顺序、交付渠道 |
| `mountSpider(host, SR)` | `CHECKS`、`CODESETS` | 质检项、执行代码示例 |
| `mountSpider(host, SR)` | `PRICE` | token 示例单价（¥ / 百万 token） |
| `mountSpider(host, SR)` | `TOKR`、`INR` | 各 agent 工作时每秒 token、输入占比 |
| `mountSpider(host, SR)` | `BUDGET`、`DAY_TARGET` | 每分钟 token 预算、今日产出目标 |
| `mountNeural(host, SR)` | `AG`、`WF`、`CH`、`CHECKS` | 角色、工作流、渠道与质检项 |
| `mountNeural(host, SR)` | `PRICE`、`TOKR`、`INR` | token 示例单价、各 agent 用量速率、输入占比 |
| `mountNeural(host, SR)` | `DAY_TARGET`、`PER_MIN` | 今日产出目标、初始化历史交付量的每分钟基准 |
| `mountNeural(host, SR)` | `AMBIENT` | 背景粒子与流星；`chatter`、`spark`、`meteor`、`burst` 默认均为 0 |
| `mountFactory(host, SR)` | `AG`、`WF`、`CH`、`CHECKS` | 机器人岗位、工作流、渠道与质检项 |
| `mountFactory(host, SR)` | `PROJECTS` | 总工程名称、载具类型、8 个子板块及对应工作流索引 |
| `mountFactory(host, SR)` | `VEH` | 载具类型、部件、尺寸与总装显示参数 |
| `mountFactory(host, SR)` | `PRICE`、`TOKR`、`INR` | token 示例单价、用量速率、输入占比 |
| `mountFactory(host, SR)` 的车间布局段 | `LOOP`、`ROAD`、`WS`、`MPT` | 主传送带、AGV 道路、工区与机器位置 |
| `mountNebula(host, SR)` | `AG`、`WF` | 角色、星云配色、各工区词库（`words`）、工作流与需求名 |
| `mountNebula(host, SR)` | `VAGUE`、`PASS`、`AXES` | 模糊词与补齐文本、评分阈值、七维雷达标签 |
| `mountNebula(host, SR)` 的星图布局段 | `ORBITS`、`CORE_Y`、`CORE_R` | 三圈轨道尺寸、星云数量与周期、星核高度与半径 |
| `mountForge(host, SR)` | `AGENTS`、`JOBS` | 8 个子 Agent 的岗位、颜色与心跳文案；示例工单、投影类型、零件任务与负责 Agent |
| `mountForge(host, SR)` | `FORM_DEFS`、`FORMS` | 六种投影的几何定义与采样数据；零件顺序需与 `JOBS.parts` 对应 |
| `mountForge(host, SR)` 的工单状态机段 | `PHASES`、`PDUR`、`PART_T` | 内部八阶段、各阶段时长与单个零件锻造时长 |
| `mountForge(host, SR)` | `ST`、`TEL`、`DELIV` | 当前工单与零件状态、模拟遥测初值、示例交付记录 |
| `mountForge(host, SR)` 的布局段 | `MODES`、`CAM`、`L` | 三档视角、透视参数、缩放与窄屏布局 |
| 系列外壳脚本 | `THREE_CDN`、`THREE_DEPS` | NEURAL、FACTORY、NEBULA 共用的 CDN 基址与按需脚本列表；FORGE 不使用这组依赖 |

配色在对应 `<template>` 内的 `<style>` 中。OPS 使用 `:host` 定义纸面配色，使用 `:host([data-theme="dark"])` 和系统深色媒体查询定义粒子荧光配色；Canvas 从这些变量读取颜色。

### 接入真实数据的改造方向

当前没有现成的数据连接器或后端服务。下面是改造入口，需要开发者自行实现接口、字段映射、状态更新与错误处理。

- **OPS**：`mountOps` 中的 `tasks`、`agents`、`wfs` 保存模拟状态，`step()` 每 900 毫秒更新，`renderAll()` 刷新面板。可替换模拟更新逻辑，将业务接口返回的数据映射到这些状态；日志可通过 `log(verb, task)` 追加，动作包括 `read`、`build`、`check`、`review`。
- **SPIDER**：`mountSpider` 中的 `simStep(dt)` 驱动任务接力模拟，`tokenStep(dt)` 生成 token 用量；任务、角色、质检、账本和可视化相互关联。接入时需要将真实运行事件和用量记录映射到相应状态，并替换模拟推进与初始化数据，避免模拟值与真实指标混用。
- **NEURAL**：`mountNeural` 内有独立的模拟状态与 `simStep(dt)`，维护任务、角色、信号脉冲及 token 状态。需要替换模拟初始化与推进逻辑，将真实事件映射到面板和 3D 信号。修改 SPIDER 的配置不会自动同步到 NEURAL。
- **FACTORY**：`mountFactory` 的「3. 模拟」段维护总工程、子板块、货箱、工区与 token 状态，由 `simStep(dt)` 推进。接入需要将真实工程、工序交接、返工与交付事件映射到这些状态，替换示例初始化及模拟推进。`PROJECTS` 的 8 个子板块、工作流索引与 `VEH` 部件需保持对应关系。
- **NEBULA**：`mountNebula` 的「3. 模拟」段由 `newTask()` 生成需求，`simStep(dt)` 推进审查，`calcScore()` 计算示例评分；`VAGUE` 的问答与 `PASS` 阈值均为演示配置。接入真实需求需要自行实现文本解析、追问与回答、评分证据和派单接口，并替换模拟初始化、读词与评分流程。
- **FORGE**：`mountForge` 的 `updateState(dt)` 按固定时长推进工单，`startPart()`、`completePart()` 与 `addDelivery()` 更新零件和交付，`heartbeat()` 生成示例事件；`updateUI()`、`updateOp()`、流光生成逻辑等还会生成负载、队列、token 与吸积指标。接入需要把真实工单、子任务、运行事件、用量和交付记录映射到 `JOBS`、`ST`、`AG`、`TEL` 与 `DELIV`，替换固定时长推进、随机指标及示例初值。新增投影需同时维护 `FORM_DEFS` 与工单零件的对应关系；只修改工单文案不会连接真实 Agent。
- `PRICE`、`TOKR`、`INR` 等参数的调整只会改变演示，不会自动接入真实账单或 agent 执行记录。

## 新增主题的步骤

1. 新建 `<template id="tpl-xxx">`，放入主题的 `<style>` 与页面结构，样式中使用 `:host` 代替 `:root`；同时添加对应的主题 host 容器。
2. 新建 `mountXxx(host, SR)` 函数，用 `SR.querySelector` 查询主题元素。在动画循环中跳过隐藏主题，并为定时刷新添加对应检查。
3. 在页面末尾外壳脚本的 `THEMES` 和 `ORDER` 中登记主题。
4. 在主题面板 `.pk-list` 中加入卡片，设置对应的 `data-theme-id`。
5. 在主题里放一个带 `data-series-pick` 属性的按钮，用于打开主题面板。需要外部库时，可参照 NEURAL 在 `THEMES` 中的 `deps` 列表登记按需依赖。

## 技术说明

- 单文件 HTML，无构建步骤。OPS 与 SPIDER 使用原生 JavaScript + CSS + Canvas 2D；NEURAL、FACTORY 与 NEBULA 使用 three.js（WebGL）与后处理效果；FORGE 使用原生 WebGL 绘制星核与投影，Canvas 2D 绘制线束、流光和 HUD，不依赖 three.js。
- 系列外壳按需挂载主题；每款主题由 `<template>`、独立 Shadow DOM 与对应的 `mountXxx(host, SR)` 函数组成。选择保存在 localStorage 的 `agent-series-theme` 中。
- **three.js 按需依赖**：首次切入 NEURAL、FACTORY 或 NEBULA 时，从 `https://cdn.jsdelivr.net/npm/three@0.147.0/` 依次加载 `build/three.min.js`，以及 `examples/js` 下的 CopyShader、LuminosityHighPassShader、EffectComposer、RenderPass、ShaderPass、UnrealBloomPass。这三款主题使用同一份 `THREE_DEPS`，正常加载完成后可复用。建议首次加载完成后再切换另一款使用 three.js 的主题；加载中快速切换可能重复请求或缺少辉光，异常时刷新重试。打开 OPS、SPIDER 或 FORGE 时不会请求这组脚本。
- **3D 故障提示**：四款 WebGL 主题在无法初始化 WebGL 时显示画面不可用提示，数据面板仍可运行，OPS 与 SPIDER 不受影响。NEURAL、FACTORY、NEBULA 的依赖加载失败也会触发提示；网络请求长时间无响应可能延迟这三款主题初始化，恢复后可刷新重试。若仅辉光后处理不可用，源码会关闭辉光渲染。FORGE 没有这组外部脚本依赖。
- 字体为 Archivo、JetBrains Mono、Noto Sans SC、Michroma、Big Shoulders Stencil Display（FACTORY 标题）、Syncopate（NEBULA 与 FORGE 标题），经 Google Fonts 加载。字体无法加载时回退至系统字体；完全离线使用需要自行本地化字体及 NEURAL、FACTORY、NEBULA 的依赖脚本。
- 系统的 `prefers-reduced-motion` 设置不会让大屏默认停住；部分 CSS 动画及故障闪烁仍会降级。FORGE 在挂载时读取该设置，减少流光、停止自动环绕与 HUD 转动，并减慢模拟与零件转动。
- OPS 的部分静态图层使用离屏画布缓存；荧光发光会增加渲染开销。不支持 Canvas 柔光或锥形渐变时，相关效果会降级。

## 目录结构

```text
agent-display/
├── index.html          # 六款主题与系列外壳（HTML + CSS + JS）
├── README.md
├── CHANGELOG.md
└── LICENSE             # PolyForm Noncommercial 1.0.0
```

当前版本为 **v6.0（2026-10-24）**：新增 FORGE 视界熔炉，主题面板预留第 07 款位置；FACTORY 的示例任务「下单系统上线」改为「预约系统上线」。版本记录见 [CHANGELOG.md](CHANGELOG.md)。

## 致谢

OPS 纸面工程的视觉风格灵感来自网上流传的 Claude Code「Paper Lab」演示视频（纸面工程图 / 夜间荧光两种风格）。本项目为独立实现，代码和示例数据均为原创，与原视频作者及 Anthropic 没有关联。

DEVELOPED BY @赛博老爸

## 授权 License

本项目源码公开，采用 **[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0)**（SPDX：`PolyForm-Noncommercial-1.0.0`），许可证全文见仓库里的 [`LICENSE`](./LICENSE) 文件。

一句话：**非商业用途免费用，商业用途要授权。**

### ✅ 可以免费做的

- 个人学习、研究、测试，自己在电脑上用，当桌面、当摆件都行。
- 修改代码、做二次创作，只要不用于商业用途。
- 学校、科研机构、公益组织、政府机构使用（不受经费来源限制）。
- 非商业地转发、分享，转发时请附上许可证（或许可证链接）和下面的版权声明。

### ❌ 未经授权不可以做的

- 公司或个体经营者在业务中使用，包括只在公司内部使用。
- 交付给客户、集成进付费产品或付费服务。
- 打包出售、二次售卖源码或安装包。
- 其他以营利为目的的使用。

### 必须保留的版权声明

使用、修改或转发时，请保留 `LICENSE` 文件开头这一行：

```
Required Notice: Copyright (c) 2026 赛博老爸
```

### 💼 商业授权

想用于商业用途，请联系 **@赛博老爸** 获取商用授权：[cyberdaddyleo@outlook.com](mailto:cyberdaddyleo@outlook.com)

### 版本说明

- 本项目自 **v5.0** 起采用 PolyForm Noncommercial License 1.0.0。
- v5.0 之前已经发布的版本，按其发布时附带的许可证执行。

> 以上中文说明仅帮助理解，具体权利和义务以英文许可证原文为准。
