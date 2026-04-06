# InfoGet 项目工作日志

> 本文件记录项目所有工作动态，供团队查阅和追溯。
> 格式：日期 + 事件 + 详细内容

---

## 2026-04-06 项目初始化

### 项目状态
- 项目目录：`/Users/Zhuanz/personalmac/InfoGet`
- 状态：空项目，刚初始化 git
- 分支：main

### 待办事项
- [x] 了解项目需求：爬取 Qwen Code 博客，转换为 RSS
- [ ] 搭建项目结构
- [ ] 实现爬虫 + RSS 生成

### 2026-04-06 15:00 接到首个开发任务
- 用户需求：爬取 https://qwenlm.github.io/qwen-code-docs/zh/blog/ 的文章
- 目标：转换为 RSS 格式，方便阅读
- 后续规划：用户提到未来会有爬虫集群，当前先完成单站爬虫
- 技术选型：决定使用 Python（适合爬虫，生态丰富）
- RSS 格式标准：RSS 2.0

### 2026-04-06 15:10 开始实现爬虫
- 使用 web_fetch 成功提取 15 篇文章的标题、日期、作者、摘要
- 链接无法通过 web_fetch 直接获取，需要直接请求页面获取完整 URL
- 准备创建 Python 项目实现爬虫

### 2026-04-06 16:36 爬虫测试成功
- 运行 `python main.py --quick` 成功
- 成功爬取 15 篇文章，包含完整标题、日期、作者、摘要、链接
- RSS 文件生成在 output/feed.xml
- 支持两种模式：--quick（快速）和 完整模式（访问每篇文章详情）

### 2026-04-06 16:40 项目提交完成
- git 提交完成，commit: a3963d1
- 11 个文件变更，1321 行新增
- 项目结构完整，测试通过

### 2026-04-06 17:00 CL0 评估与新需求
- 完成 CL0 全面评估，综合评分 7.0/10
- 发现严重问题：WORKLOG.md 未被 .gitignore 忽略
- ai-doc/WORKLOG.md 内容过时未同步

### 2026-04-06 17:05 新需求：本地 RSS 服务器
- 用户反馈：RSS 文件在本地无法直接访问，需要搭建本地 HTTP 服务器
- 需求：在项目中添加本地 HTTP 服务器功能，让用户可以通过浏览器/RSS阅读器访问 feed.xml

### 2026-04-06 17:10 服务器功能实现完成
- 新建 scraper/server.py：HTTP 服务器核心模块（零依赖，标准库实现）
- 新建 server.py：独立启动脚本
- 修改 main.py：添加 --serve 参数
- 端点：GET / (状态页), GET /feed (RSS XML), GET /health (健康检查)
- 测试通过：三个端点均正常响应

### 2026-04-06 17:15 代码审查与安全修复
- code-reviewer 审查发现 2 个严重安全问题：
  - 🔴 XSS 漏洞：动态内容未转义直接插入 HTML
  - 🔴 路径遍历漏洞：未验证 RSS 文件路径
- 已修复所有严重问题和中等问题
- 修复内容：html.escape() 转义、路径规范化验证、信号处理器冲突修复

### 2026-04-06 17:16 修复 html 模块导入冲突
- 用户反馈：访问 404 页面时出现 UnboundLocalError: local variable 'html' referenced before assignment
- 根因分析：code-debugger 修复时虽然将 import html 移到了文件顶部，但多个方法内有 `html = ...` 赋值语句
  - Python 将方法内的 `html` 视为局部变量，遮蔽了顶层的 `import html` 模块
  - 导致在 f-string 中使用 `html.escape()` 时，html 被认为是未赋值的局部变量
- 修复方案：将所有方法内的局部变量 `html` 重命名为 `html_content`
- 涉及方法：_serve_index, _serve_404, _build_status_html
- 测试验证：所有端点（/, /feed, /health, 404页面）均正常工作

### 2026-04-06 17:20 用户选择爬取记录方案
- 用户反馈：询问当前爬取记录的保存方式
- 当前问题：无持久化记录、无增量更新、无失败记录、无历史记录、无去重机制
- 用户选择：方案 B - SQLite 数据库
- 理由：结构化、支持增量更新/去重/查询、为未来爬虫集群做准备

### 待办事项
- [x] 设计 SQLite 数据库 schema（文章表、爬取记录表）
- [x] 实现数据库操作模块
- [x] 改造爬虫支持增量更新和去重
- [x] 添加爬取历史查询 API
- [x] 更新服务器端点展示爬取状态
- [x] 修复 exists_count 列缺失问题（数据库迁移）
- [x] 修复 server.py 缺少 --db 参数

### 2026-04-06 17:50 完成全覆盖测试
- 用户询问：测试写好了吗？→ 回答没有，立即补上
- 用户选择：全覆盖测试（数据库、RSS生成器、爬虫解析、HTTP服务器端点）
- 结果：82 个测试全部通过，用时 1.29 秒

测试覆盖：
- tests/test_database.py (27个)：建表、CRUD、增量更新、爬取记录、失败记录、线程安全
- tests/test_rss_generator.py (15个)：RSS生成、版本合规性、XML转义、降级、边界情况
- tests/test_scraper.py (14个)：Article序列化、URL日期提取、列表页解析、去重
- tests/test_server.py (26个)：所有HTTP端点（有/无数据库）、404、RSS提取、响应发送

技术要点：
- 零额外依赖：仅使用 pytest + unittest.mock + BeautifulSoup4
- 完全隔离：每个测试使用独立临时数据库，不污染真实数据
- 无网络请求：爬虫测试使用模拟HTML，服务器测试使用mock对象

### 2026-04-06 18:30 Cron 迁移到容器内
- 用户建议：cron 放到 Docker 容器内部，服务器无需额外配置
- 实现方案：
  - Dockerfile 安装 cron + curl
  - 配置 /etc/cron.d/infoget（3 条定时任务）
  - 创建 docker-entrypoint.sh 同时启动 cron + HTTP 服务器
  - deploy.sh 移除宿主机 crontab 配置
- 定时任务（容器内）:
  - 每 6 小时快速更新
  - 每天凌晨 3 点完整爬取
  - 每周日凌晨 2 点输出统计
- 验证通过：手动触发 + 自动验证（3 次重试）

### 2026-04-06 18:00 Docker 打包完成
- Dockerfile: 多阶段构建(builder→tester→runner)，cron内置，健康检查
- docker-compose.yml: 数据持久化、端口映射、资源限制
- .dockerignore: 排除不必要文件
- 构建成功，镜像名: infoget-infoget
- 容器验证:
  - 健康检查: GET /health → {"status": "ok"} ✅
  - 统计API: GET /api/stats → 15篇文章，3次爬取 ✅
  - 爬虫运行: 容器内执行 main.py --quick 成功 ✅
  - RSS访问: GET /feed → 正常返回 RSS 2.0 XML ✅

---
