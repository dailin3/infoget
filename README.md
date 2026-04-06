# Qwen Code Docs Blog RSS Generator

爬取 [Qwen Code Docs 博客](https://qwenlm.github.io/qwen-code-docs/zh/blog/) 文章，生成标准 RSS 2.0 格式的 XML 文件。

## 功能特性

- ✅ 自动爬取博客列表页的所有文章
- ✅ 提取文章标题、发布日期、作者、摘要、完整链接
- ✅ 生成标准 RSS 2.0 格式 XML 文件
- ✅ 支持两种模式：完整模式（访问详情页）和快速模式（仅列表页）
- ✅ 内置本地 HTTP 服务器，可通过浏览器或 RSS 阅读器直接访问
- ✅ 可配置请求延迟，礼貌爬取
- ✅ 详细的代码注释，适合初级工程师理解

## 项目结构

```
.
├── main.py                    # 主入口文件
├── server.py                  # 本地 HTTP 服务器启动脚本
├── requirements.txt           # Python 依赖
├── README.md                  # 项目说明
├── scraper/                   # 爬虫模块
│   ├── __init__.py           # 模块初始化
│   ├── scraper.py            # 博客爬虫实现
│   ├── rss_generator.py      # RSS 生成器
│   └── server.py             # HTTP 服务器核心模块
└── output/                    # 输出目录
    └── feed.xml              # 生成的 RSS 文件（运行后生成）
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 运行

**爬取 + 生成 RSS**：

完整模式（推荐，信息更完整）：
```bash
python main.py
```

快速模式（仅爬取列表页，速度更快）：
```bash
python main.py --quick
```

**启动本地 HTTP 服务器**：

独立启动服务器（默认端口 8080）：
```bash
python server.py
```

指定端口：
```bash
python server.py --port 9000
```

爬取完成后自动启动服务器：
```bash
python main.py --quick --serve
```

### 3. 访问 RSS

启动服务器后，可通过以下地址访问：

| 地址 | 说明 |
|------|------|
| `http://127.0.0.1:8080/` | 状态页面（文章列表、统计信息） |
| `http://127.0.0.1:8080/feed` | RSS 2.0 XML（用于 RSS 阅读器订阅） |
| `http://127.0.0.1:8080/health` | 健康检查端点 |

在 RSS 阅读器中添加订阅：`http://127.0.0.1:8080/feed`

**指定输出文件**：
```bash
python main.py --output my_feed.xml
```

**调整请求延迟**：
```bash
python main.py --delay 2.0
```

### 3. 查看帮助

```bash
python main.py --help
```

## 命令行参数

| 参数 | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--quick` | | flag | False | 快速模式，不访问文章详情页 |
| `--output` | `-o` | string | `output/feed.xml` | 输出文件路径 |
| `--delay` | `-d` | float | 1.0 | 每次请求之间的延迟（秒） |

## 技术栈

- **Python 3.10+**
- **requests**: HTTP 请求库
- **BeautifulSoup4**: HTML 解析库
- **lxml**: 高性能 XML/HTML 解析器
- **feedgen** (可选): RSS/Atom Feed 生成库

## 输出示例

生成的 RSS 文件 (`output/feed.xml`) 格式如下：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Qwen Code Docs 博客</title>
    <link>https://qwenlm.github.io/qwen-code-docs/zh/blog/</link>
    <description>Qwen Code 官方文档博客文章的 RSS 订阅源</description>
    <language>zh-CN</language>
    <item>
      <title>文章标题</title>
      <link>https://qwenlm.github.io/qwen-code-docs/zh/blog/some-article/</link>
      <description>文章摘要...</description>
      <dc:creator>作者名称</dc:creator>
      <pubDate>Mon, 06 Apr 2026 00:00:00 GMT</pubDate>
      <guid isPermaLink="true">https://qwenlm.github.io/qwen-code-docs/zh/blog/some-article/</guid>
    </item>
    <!-- 更多文章... -->
  </channel>
</rss>
```

## 使用说明

### 在 RSS 阅读器中订阅

将生成的 `output/feed.xml` 文件：
1. 上传到任意可公开访问的 URL
2. 或在本地直接用 RSS 阅读器打开

### 定时更新

项目内置定时更新脚本，位于 `scripts/update_feed.sh`。

**使用 cron 自动更新**：
```bash
# 安装定时任务
crontab scripts/crontab.txt

# 查看当前任务
crontab -l
```

**手动更新**：
```bash
bash scripts/update_feed.sh
```

## 注意事项

1. **礼貌爬取**: 默认请求间隔为 1 秒，请勿设置过短的延迟
2. **页面结构**: 如果目标网站页面结构发生变化，可能需要更新解析逻辑
3. **网络问题**: 确保运行环境可以访问目标网站
4. **feedgen 可选**: 如果 feedgen 安装失败，程序会自动使用手动拼接方式生成 RSS

## 开发

### 代码结构说明

- `scraper/scraper.py`: 包含 `QwenBlogScraper` 类，负责爬取网页
  - `_fetch_page()`: 获取单个网页
  - `_parse_list_page()`: 解析博客列表页
  - `_parse_article_detail()`: 解析文章详情页
  - `scrape()`: 主爬取方法

- `scraper/rss_generator.py`: 包含 `RSSGenerator` 类，负责生成 RSS
  - `_try_feedgen()`: 使用 feedgen 库生成
  - `_manual_rss()`: 手动拼接 XML
  - `generate()`: 主生成方法
  - `save_to_file()`: 保存到文件

### 扩展建议

- 添加缓存机制，避免重复请求
- 支持增量更新（只爬取新文章）
- 添加更多错误重试逻辑
- 支持输出 Atom 格式

## 服务器部署

### 一键部署

将项目上传到服务器后，运行：

```bash
# 以 root 身份运行
sudo bash scripts/deploy.sh
```

脚本会自动：
1. 检查并安装 Docker / Docker Compose（如未安装）
2. 构建并启动服务
3. 首次爬取博客文章
4. 配置 cron 定时任务（每 6 小时更新）
5. 设置日志文件

### 手动部署

```bash
# 1. 上传项目到服务器
scp -r InfoGet/ user@server:/opt/infoget/

# 2. 在服务器上启动
cd /opt/infoget
docker compose up -d --build

# 3. 生成初始数据
docker compose exec infoget python main.py --quick

# 4. 安装定时任务
crontab scripts/crontab.txt
```

## License

MIT
