# 候一会 WaitWise — 餐厅动态候位与智能叫号系统（UI 初版 v0.1）

> 《高级软件体系结构》小组课程设计的**可运行 UI/业务原型**。参考真实餐厅排队体验构思，但与大众点评及任何真实餐厅均无关联。该版本重点是**先看界面、再和组员修改**；不是最终课程交付或生产级系统。

## 1. 三分钟开始体验（GitHub Codespaces）

1. 打开本仓库 `wjwillac/waitwise`，已经包含完整源代码和 Codespaces 配置。
2. 仓库主页点击 **Code → Codespaces → Create codespace on main**。
3. Codespaces 根据 `.devcontainer/devcontainer.json` 创建 Python 开发容器，并自动执行 `pip install -r requirements.txt`。
4. 打开 Codespaces 的终端，输入：

   ```bash
   ./start.sh
   ```

5. 打开自动转发的 **8000** 端口：
   - 顾客端：`/`
   - 商家端：`/staff`
   - API 文档：`/docs`
6. 演示商家 PIN：`123456`。

> 本仓库已配置 `.devcontainer/devcontainer.json`。在 GitHub Codespaces 中首次创建开发环境后，会自动执行依赖安装。

如果你想从 Codespaces 终端上传自己的仓库，也可以安装 GitHub CLI 并执行 `git init / git add / git commit / git remote add / git push`；前提是你已有写入权限，并完成 GitHub 验证。

## 2. 不使用 Codespaces，本地也能运行

Python 3.11+：

```bash
python -m pip install -r requirements.txt
./start.sh
```

访问 `http://localhost:8000`。首次启动自动建 SQLite 数据库并初始化 6 个演示取号和 5 张餐桌。默认 DB 路径为 `./data/waitwise.sqlite3`。如果已经有数据库，不会重复造演示记录。

Windows 可用：

```bash
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 --reload
```

## 3. 页面布局与修改入口

| 位置 | 文件 | 修改内容 |
|---|---|---|
| 顾客页面结构 | `frontend/app.js` 中 `customerPage()`、`hero()`、`customerForm()`、`ticketSection()` | 标题、表单、候位卡、引导流程 |
| 商家工作台结构 | `frontend/app.js` 中 `staffPage()`、`ticketsTable()`、`tablesPanel()` | 数据卡片、叫号按钮、队列/餐桌布局 |
| 全部样式 | `frontend/styles.css` | 字体、颜色、边距、响应式布局 |
| 默认规则 | `.env.example`，实际部署可用环境变量 | 宽限分钟数、模拟电话承诺分钟数 |
| 核心排队逻辑 | `backend/service.py` | 跳过未到店、优先级、桌位分配、电话提醒 |
| HTTP 路由 | `backend/app.py` | API 入参、操作接口、商家 PIN 校验 |
| 数据库表 | `backend/storage.py` | 用户候位、餐桌、事件、通知数据 |
| 事件订阅者 | `backend/events.py` | 事件记录与站内提醒投影 |

**前端没有 React/Vue 或构建依赖**，是原生 HTML/CSS/ES Modules，保存文件后刷新页面就能看到变化，适合你和组员先反复讨论界面。前端与后端分文件夹，通过 `/api/*` 通信，共用 8000 端口。

## 4. 演示操作（两个人一起看最好）

| 顾客端 | 商家端 |
|---|---|
| 1. 输入姓名、用餐人数、预计到店时间，点击“立即取号” | 1. 打开 `/staff`，输入 PIN 123456 |
| 2. 查看自己的候位号码和前方等待桌数 | 2. 查看排队列表及桌位空闲情况 |
| 3. 顾客尚未到店时，暂不点击“我已到店” | 3. 点击空桌的“智能叫号”，系统会跳过未到店者 |
| 4. 等被跳过后，在宽限期内点击“我已到店” | 4. 再次点击“智能叫号”，优先安排恢复资格的顾客 |
| 5. 预计时间到后，出现“模拟电话确认”；选择“10 分钟内能到” | 5. 点击右下角“+10 分钟”快进演示时钟 |
| 6. 也可取消候位 / 修改预计到店时间 | 6. 完成“叫号 → 确认入座 → 结束用餐” |

**注意**：真正的外呼电话**尚未集成**。预计到店时间触发的是“电话确认事件 + 顾客页面弹出模拟确认”。后续可以接入合规的通信服务，不能把这个原型说成已实际打通运营商外呼。

## 5. 当前默认业务规则（待你和小组调整）

- 用户**立即取正式号码**，并填写预计到店时间。
- 服务员为可用餐桌发起叫号时，系统筛选符合餐桌容量的顾客；尚未到店者被**暂缓**，不会占着空桌。
- 曾经提前被跳过、且在**预计到店时间 +30 分钟内**到店者，获得该桌型的**优先候位资格**，但不会打断已经入座的顾客。
- 预计到店时间到、仍未登记到店，则**触发模拟电话确认**，询问能否在 10 分钟内到达。
- 承诺 10 分钟后仍未到店，演示规则是**取消额外优先权**；超过预计时间 30 分钟仍未到店则过期。
- 当前演示允许顾客修改预计到店时间、主动取消。**是否限制修改次数/是否允许反复修改时间**尚未最终讨论。
- 餐桌分配目前使用**先符合容量、再按优先资格与取号顺序**的简单规则，不是机器学习预测，也不保证最优翻台率。
- 页面和默认规则均是 **v0.1 可讨论的原型**，不是你已经最终同意的全部业务规定。

## 6. 软件体系结构和设计—实现对应

整体采用**客户端—服务器 + 分层式模块化单体 + 进程内事件机制**。

```text
frontend/app.js, styles.css       客户端表示层
       │ HTTP JSON
       ▼
backend/app.py                   API/鉴权适配层
       │
       ▼
backend/service.py               业务服务：取号、到店、叫号、桌位分配、超时检查
       │                         (事务处理 + 状态机)
       ├──────────────► backend/events.py
       │                     领域事件持久化 + 通知订阅者
       ▼
backend/storage.py               SQLite 数据访问与事务层
       ▼
SQLite: tickets, tables, events, notifications
```

**事件驱动证据**：`TicketCreated`、`TicketDeferred`、`ArrivalReminder`、`ArrivalConfirmed`、`TicketCalled`、`TableReleased`、`TicketExpired` 等领域事件保存在 `events` 表；`backend/events.py` 内的订阅规则在同一事务中派生站内提醒；`service.tick()` 是时间事件扫描器，后台任务每 8 秒检查。没有假装它是 Kafka 多进程微服务。

**一致性证据**：取号编号计数器和餐桌状态分配均在 `BEGIN IMMEDIATE` SQLite 写事务中执行；同一空桌不能同时赋予两个排队记录。POST 新增取号支持 `request_id` 幂等键，避免网络重试导致重复取号。

**待优化问题**：进程内事件依然与数据库事务同步执行，若未来需要真实电话发送、跨系统消息，应升级为事件 Outbox + 异步 worker，并加入重试/去重/失败告警。当前不声称有分布式容错能力。

## 7. 测试

```bash
python -m pytest -q
```

当前已测试包括：页面入口、取号幂等、并发编号唯一性、管理鉴权、跳过未到店、叫号/入座/结束、到店优先、模拟电话提醒、宽限期过期、取消与演示重置。

> 真实 Codespaces 的首次依赖安装和页面打开仍需你把项目上传后验证；此处的 API 测试结果来自本地隔离运行环境。

## 8. 演示限制与安全边界

- 演示 PIN 是弱认证方式；生产环境需用户账号认证、角色权限、HTTPS、CSRF 防护、速率限制和审计。
- 演示顾客详情使用 ID 获取，**不具备真正的用户数据隔离**；切勿录入真实顾客个人信息。上线前必须改为鉴权的票据查询方式。
- 浏览器每 5 秒刷新队列；后续可升级为 WebSocket/SSE 实时推送。
- 图片和布局为课程项目原创示意，不属于真实商家。餐厅名称、桌数和顾客均为模拟。
- 本项目没有集成大众点评 API、短信、真实电话、支付功能，也没有接入 AI 预测模型。
- 通过真实业务调研和小组评审后，再决定是否引入预测调度、商家规则编辑和线上登录。
