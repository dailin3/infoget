"""
本地 HTTP 服务器模块
-------------------
提供本地 Web 服务，让用户可以通过浏览器或 RSS 阅读器访问生成的 RSS Feed。

功能：
1. GET /          → 返回 HTML 状态页面（文章列表、服务器状态）
2. GET /feed      → 返回 RSS XML 内容（Content-Type: application/rss+xml）
3. GET /health    → 返回健康检查 JSON（{"status": "ok"}）
4. GET /api/stats → 返回综合统计信息
5. GET /api/history → 返回爬取历史
6. GET /api/articles → 返回文章列表（支持分页）
7. GET /api/failures → 返回失败记录

技术实现：
- 仅使用 Python 标准库（http.server, json, os 等）
- 零额外依赖
"""

import html
import json
import os
import re
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Optional
from urllib.parse import urlparse, parse_qs

# 可选导入数据库模块
try:
    from .database import InfoGetDB
    from .scraper import Article
    from .rss_generator import RSSGenerator
except ImportError:
    InfoGetDB = None
    Article = None
    RSSGenerator = None


class RSSFeedHandler(SimpleHTTPRequestHandler):
    """
    RSS Feed HTTP 请求处理器
    ----------------------
    处理不同路径的请求，返回对应的内容。
    """

    # RSS 文件默认路径（相对于项目根目录）
    DEFAULT_FEED_PATH = "output/feed.xml"

    def __init__(self, *args, feed_path: str = None, db_path: str = None, **kwargs):
        """
        初始化请求处理器

        参数:
            feed_path: RSS 文件的绝对路径或相对路径
            db_path: 数据库文件路径（可选）
        """
        # 路径遍历漏洞修复：验证 feed_path 必须在项目目录内
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if feed_path:
            abs_feed_path = os.path.abspath(feed_path)
        else:
            abs_feed_path = os.path.abspath(os.path.join(project_root, self.DEFAULT_FEED_PATH))

        # 确保路径在项目根目录内
        if not abs_feed_path.startswith(os.path.abspath(project_root)):
            raise ValueError(f"feed_path 必须在项目目录内: {feed_path}")

        self.feed_path = abs_feed_path

        # 初始化数据库连接（可选）
        self.db: Optional[InfoGetDB] = None
        if db_path and InfoGetDB is not None:
            try:
                self.db = InfoGetDB(db_path)
            except Exception as e:
                print(f"[服务器] 数据库初始化失败: {e}")

        super().__init__(*args, **kwargs)

    def do_GET(self):
        """处理 GET 请求"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path.rstrip("/")

        # 路由分发
        if path == "" or path == "/index.html":
            self._serve_index()
        elif path == "/feed":
            self._serve_feed()
        elif path == "/health":
            self._serve_health()
        elif path == "/api/stats":
            self._serve_api_stats()
        elif path == "/api/history":
            self._serve_api_history()
        elif path == "/api/articles":
            self._serve_api_articles(parsed_path)
        elif path == "/api/failures":
            self._serve_api_failures()
        else:
            self._serve_404()

    def _serve_index(self):
        """返回 HTML 状态页面"""
        try:
            # 读取 RSS 文件，解析文章信息
            if not os.path.exists(self.feed_path):
                html_content = self._build_error_html("RSS 文件不存在", "请先运行爬虫生成 RSS Feed")
                self._send_html(html_content, status=404)
                return

            # 读取 feed.xml 内容
            with open(self.feed_path, "r", encoding="utf-8") as f:
                feed_content = f.read()

            # 从 XML 中提取文章信息（简单的字符串解析）
            articles = self._extract_articles_from_rss(feed_content)

            # 构建 HTML 页面
            html_content = self._build_status_html(articles, feed_content)
            self._send_html(html_content)

        except Exception as e:
            html_content = self._build_error_html("服务器内部错误", str(e))
            self._send_html(html_content, status=500)

    def _serve_feed(self):
        """
        返回 RSS XML 内容
        ----------
        优先从数据库动态生成 RSS（确保数据一致性）。
        如果数据库未启用，降级为读取文件。
        """
        try:
            if self.db:
                # 从数据库动态生成（唯一真实数据源）
                articles_data = self.db.get_all_articles(order_by="pub_date DESC")
                if not articles_data:
                    self._send_json(
                        {"error": "数据库中暂无文章", "hint": "请先运行爬虫爬取文章"},
                        status=404,
                    )
                    return

                # 将数据库记录转为 Article 对象
                articles = []
                for a in articles_data:
                    articles.append(Article(
                        title=a["title"],
                        url=a["url"],
                        pub_date=a["pub_date"],
                        author=a.get("author", ""),
                        summary=a.get("summary", ""),
                    ))

                # 动态生成 RSS
                generator = RSSGenerator(
                    title="Qwen Code Docs 博客",
                    link="https://qwenlm.github.io/qwen-code-docs/zh/blog/",
                    description="Qwen Code 官方文档博客文章的 RSS 订阅源",
                    language="zh-CN",
                    author="Qwen Team",
                )
                rss_content = generator.generate(articles)
            else:
                # 降级：读取文件（兼容无数据库模式）
                if not os.path.exists(self.feed_path):
                    self._send_json(
                        {"error": "RSS 文件不存在", "path": self.feed_path},
                        status=404,
                    )
                    return
                with open(self.feed_path, "r", encoding="utf-8") as f:
                    rss_content = f.read()

            # 设置正确的 Content-Type
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
            self.send_header("Content-Length", str(len(rss_content.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(rss_content.encode("utf-8"))

        except Exception as e:
            self._send_json(
                {"error": "获取 RSS 失败", "detail": str(e)},
                status=500,
            )

        except Exception as e:
            self._send_json(
                {"error": "读取 RSS 文件失败", "detail": str(e)},
                status=500,
            )

    def _serve_health(self):
        """返回健康检查响应"""
        self._send_json({"status": "ok"})

    def _serve_api_stats(self):
        """返回综合统计信息"""
        if not self.db:
            self._send_json(
                {"error": "数据库未启用", "hint": "启动服务器时指定 --db 参数"},
                status=503,
            )
            return

        try:
            stats = self.db.get_stats()
            self._send_json({"success": True, "data": stats})
        except Exception as e:
            self._send_json({"error": "获取统计信息失败", "detail": str(e)}, status=500)

    def _serve_api_history(self):
        """返回爬取历史"""
        if not self.db:
            self._send_json(
                {"error": "数据库未启用", "hint": "启动服务器时指定 --db 参数"},
                status=503,
            )
            return

        try:
            # 从查询参数获取 limit
            parsed_path = urlparse(self.path)
            params = parse_qs(parsed_path.query)
            limit = int(params.get("limit", [20])[0])
            limit = min(limit, 100)  # 最大 100 条

            history = self.db.get_crawl_history(limit=limit)
            self._send_json({"success": True, "data": history, "count": len(history)})
        except Exception as e:
            self._send_json({"error": "获取爬取历史失败", "detail": str(e)}, status=500)

    def _serve_api_articles(self, parsed_path):
        """返回文章列表（支持分页）"""
        if not self.db:
            self._send_json(
                {"error": "数据库未启用", "hint": "启动服务器时指定 --db 参数"},
                status=503,
            )
            return

        try:
            # 解析查询参数
            params = parse_qs(parsed_path.query)
            page = int(params.get("page", [1])[0])
            page_size = int(params.get("page_size", [50])[0])
            order_by = params.get("order_by", ["pub_date DESC"])[0]

            # 限制 page_size
            page_size = min(page_size, 200)
            page = max(page, 1)

            # 获取文章总数
            total = self.db.get_article_count()

            # 获取文章列表
            articles = self.db.get_all_articles(order_by=order_by)

            # 手动分页
            start = (page - 1) * page_size
            end = start + page_size
            paginated_articles = articles[start:end]

            self._send_json({
                "success": True,
                "data": {
                    "articles": paginated_articles,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
                }
            })
        except Exception as e:
            self._send_json({"error": "获取文章列表失败", "detail": str(e)}, status=500)

    def _serve_api_failures(self):
        """返回失败记录"""
        if not self.db:
            self._send_json(
                {"error": "数据库未启用", "hint": "启动服务器时指定 --db 参数"},
                status=503,
            )
            return

        try:
            # 从查询参数获取 limit
            parsed_path = urlparse(self.path)
            params = parse_qs(parsed_path.query)
            limit = int(params.get("limit", [50])[0])
            limit = min(limit, 200)  # 最大 200 条

            failures = self.db.get_failures(limit=limit)
            self._send_json({"success": True, "data": failures, "count": len(failures)})
        except Exception as e:
            self._send_json({"error": "获取失败记录失败", "detail": str(e)}, status=500)

    def _serve_404(self):
        """返回 404 错误页面"""
        html_content = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>404 - 页面未找到</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    max-width: 600px;
                    margin: 100px auto;
                    padding: 20px;
                    background: #f5f5f5;
                    color: #333;
                }}
                .error-code {{ font-size: 72px; font-weight: bold; color: #e74c3c; margin: 0; }}
                .error-msg {{ font-size: 24px; margin: 10px 0; }}
                a {{ color: #3498db; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
                .links {{ margin-top: 30px; }}
                .links a {{ display: inline-block; margin-right: 20px; padding: 10px 20px; background: #3498db; color: white; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <p class="error-code">404</p>
            <p class="error-msg">页面未找到</p>
            <p>请求的路径 <code>{html.escape(self.path)}</code> 不存在。</p>
            <div class="links">
                <a href="/">返回首页</a>
                <a href="/feed">查看 RSS Feed</a>
            </div>
        </body>
        </html>
        """
        self._send_html(html_content, status=404)

    def _extract_articles_from_rss(self, rss_content: str) -> list:
        """
        从 RSS XML 中简单提取文章信息
        （不使用 XML 解析器，采用字符串匹配，性能更好）

        参数:
            rss_content: RSS XML 字符串

        返回:
            文章信息列表，每项包含 title, link, pub_date, description
        """
        articles = []

        # 简单的 XML 解析：提取每个 <item> 块
        # 提取所有 <item> 块
        item_pattern = re.compile(r"<item>(.*?)</item>", re.DOTALL)
        items = item_pattern.findall(rss_content)

        for item in items:
            article = {}

            # 提取标题
            title_match = re.search(r"<title>(.*?)</title>", item, re.DOTALL)
            article["title"] = title_match.group(1).strip() if title_match else "无标题"

            # 提取链接
            link_match = re.search(r"<link>(.*?)</link>", item, re.DOTALL)
            article["link"] = link_match.group(1).strip() if link_match else ""

            # 提取发布日期
            pub_date_match = re.search(r"<pubDate>(.*?)</pubDate>", item, re.DOTALL)
            article["pub_date"] = pub_date_match.group(1).strip() if pub_date_match else ""

            # 提取描述
            desc_match = re.search(r"<description>(.*?)</description>", item, re.DOTALL)
            article["description"] = desc_match.group(1).strip() if desc_match else ""

            # 提取作者（dc:creator）
            author_match = re.search(r"<dc:creator>(.*?)</dc:creator>", item, re.DOTALL)
            article["author"] = author_match.group(1).strip() if author_match else ""

            articles.append(article)

        return articles

    def _build_status_html(self, articles: list, feed_content: str) -> str:
        """
        构建状态页面 HTML

        参数:
            articles: 文章信息列表
            feed_content: 原始 RSS XML 内容

        返回:
            HTML 字符串
        """
        # 计算统计信息
        article_count = len(articles)
        file_size = len(feed_content.encode("utf-8"))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 格式化文件大小
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"

        # 生成文章列表 HTML
        articles_html = ""
        if articles:
            article_items = []
            for article in articles:
                pub_date_str = ""
                if article.get("pub_date"):
                    # 尝试解析 RFC 822 日期
                    try:
                        from email.utils import parsedate_to_datetime
                        dt = parsedate_to_datetime(article["pub_date"])
                        pub_date_str = dt.strftime("%Y-%m-%d")
                    except Exception:
                        pub_date_str = article["pub_date"]

                author_str = f" · {html.escape(article['author'])}" if article.get("author") else ""

                article_items.append(f"""
                <div class="article-item">
                    <h3><a href="{html.escape(article['link'])}" target="_blank">{html.escape(article['title'])}</a></h3>
                    <div class="article-meta">
                        <span class="date">{html.escape(pub_date_str)}</span>{author_str}
                    </div>
                    {f'<div class="article-desc">{html.escape(article["description"][:150])}...</div>' if article.get("description") else ""}
                </div>
                """)
            articles_html = "\n".join(article_items)
        else:
            articles_html = "<p class='no-articles'>暂无文章</p>"

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Qwen Code Docs RSS Feed</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: #f5f7fa;
            color: #2c3e50;
            line-height: 1.6;
        }}
        .container {{ max-width: 900px; margin: 0 auto; padding: 20px; }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{ font-size: 28px; margin-bottom: 10px; }}
        .header p {{ opacity: 0.9; }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        .stat-value {{ font-size: 32px; font-weight: bold; color: #667eea; }}
        .stat-label {{ font-size: 14px; color: #7f8c8d; margin-top: 5px; }}
        .section {{
            background: white;
            padding: 25px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        .section h2 {{
            font-size: 20px;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}
        .article-item {{
            padding: 15px 0;
            border-bottom: 1px solid #eee;
        }}
        .article-item:last-child {{ border-bottom: none; }}
        .article-item h3 {{
            font-size: 18px;
            margin-bottom: 5px;
        }}
        .article-item h3 a {{
            color: #2c3e50;
            text-decoration: none;
        }}
        .article-item h3 a:hover {{ color: #667eea; }}
        .article-meta {{
            font-size: 14px;
            color: #7f8c8d;
            margin-bottom: 8px;
        }}
        .article-desc {{
            font-size: 14px;
            color: #555;
            line-height: 1.5;
        }}
        .links {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 15px;
        }}
        .btn {{
            display: inline-block;
            padding: 10px 20px;
            background: #667eea;
            color: white;
            text-decoration: none;
            border-radius: 5px;
            font-size: 14px;
            transition: background 0.3s;
        }}
        .btn:hover {{ background: #5568d3; }}
        .btn.secondary {{ background: #95a5a6; }}
        .btn.secondary:hover {{ background: #7f8c8d; }}
        .no-articles {{
            text-align: center;
            padding: 40px;
            color: #7f8c8d;
        }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #7f8c8d;
            font-size: 14px;
        }}
        code {{
            background: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📰 Qwen Code Docs RSS Feed</h1>
            <p>本地 RSS 订阅服务器 · 让你的阅读器随时获取最新文章</p>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value">{article_count}</div>
                <div class="stat-label">文章总数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{size_str}</div>
                <div class="stat-label">Feed 大小</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">✅</div>
                <div class="stat-label">服务状态</div>
            </div>
        </div>

        <div class="section">
            <h2>🔗 快速访问</h2>
            <div class="links">
                <a href="/feed" class="btn">📄 RSS Feed XML</a>
                <a href="/health" class="btn secondary">💚 健康检查</a>
            </div>
            <p style="margin-top: 15px; font-size: 14px; color: #7f8c8d;">
                复制 RSS 地址到你的阅读器：<code>{self._get_base_url()}/feed</code>
            </p>
        </div>

        <div class="section">
            <h2>📝 最新文章</h2>
            {articles_html}
        </div>

        <div class="footer">
            服务器运行时间: {now} · InfoGet RSS Server
        </div>
    </div>
</body>
</html>"""
        return html_content

    def _build_error_html(self, title: str, message: str) -> str:
        """
        构建错误页面 HTML

        参数:
            title: 错误标题
            message: 错误详情

        返回:
            HTML 字符串
        """
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>错误 - {title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 600px;
            margin: 100px auto;
            padding: 20px;
            background: #f5f5f5;
            color: #333;
            text-align: center;
        }}
        h1 {{ color: #e74c3c; }}
        a {{ color: #3498db; }}
    </style>
</head>
<body>
    <h1>❌ {html.escape(title)}</h1>
    <p>{html.escape(message)}</p>
    <p><a href="/">返回首页</a></p>
</body>
</html>"""

    def _get_base_url(self) -> str:
        """获取当前请求的基础 URL"""
        host = self.headers.get("Host", f"{self.server.server_address[0]}:{self.server.server_address[1]}")
        scheme = "http"
        return f"{scheme}://{host}"

    def _send_html(self, html: str, status: int = 200):
        """
        发送 HTML 响应

        参数:
            html: HTML 内容
            status: HTTP 状态码
        """
        content = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, data: dict, status: int = 200):
        """
        发送 JSON 响应

        参数:
            data: 要发送的字典数据
            status: HTTP 状态码
        """
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt, *args):
        """
        自定义日志格式
        简化默认的输出，更清晰地显示请求信息
        """
        # 格式: [时间] 方法 路径 状态码
        from email.utils import formatdate
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.server.request_log.info(f"[{timestamp}] {fmt % args}")


class RequestLogger:
    """简单的请求日志记录器"""

    def __init__(self):
        self.messages = []

    def info(self, message: str):
        """记录信息日志"""
        self.messages.append(message)
        # 只保留最近 100 条日志
        if len(self.messages) > 100:
            self.messages = self.messages[-100:]

    def get_recent(self, count: int = 10) -> list:
        """获取最近的日志"""
        return self.messages[-count:]


def create_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    feed_path: str = None,
    db_path: str = None,
) -> HTTPServer:
    """
    创建并配置 HTTP 服务器

    参数:
        host: 绑定地址，默认 "0.0.0.0"
        port: 监听端口，默认 8080
        feed_path: RSS 文件路径，默认 "output/feed.xml"
        db_path: 数据库文件路径（可选），启用数据库查询 API

    返回:
        配置好的 HTTPServer 实例
    """
    # 创建请求日志记录器
    request_log = RequestLogger()

    # 创建处理器工厂函数
    def handler_factory(*args, **kwargs):
        handler = RSSFeedHandler(*args, feed_path=feed_path, db_path=db_path, **kwargs)
        handler.server.request_log = request_log
        return handler

    # 创建服务器
    server = HTTPServer((host, port), handler_factory)
    server.request_log = request_log

    return server


def run_server(
    host: str = "0.0.0.0",
    port: int = 8080,
    feed_path: str = None,
    db_path: str = None,
    block: bool = True,
) -> HTTPServer:
    """
    启动 HTTP 服务器

    参数:
        host: 绑定地址，默认 "0.0.0.0"
        port: 监听端口，默认 8080
        feed_path: RSS 文件路径，默认 "output/feed.xml"
        db_path: 数据库文件路径（可选），启用数据库查询 API
        block: 是否阻塞运行，默认 True

    返回:
        运行中的 HTTPServer 实例
    """
    server = create_server(host=host, port=port, feed_path=feed_path, db_path=db_path)

    print(f"\n{'=' * 60}")
    print("🌐 RSS Feed 服务器已启动")
    print(f"{'=' * 60}")
    print(f"   监听地址: http://{host if host != '0.0.0.0' else '127.0.0.1'}:{port}")
    print(f"   状态页面: http://127.0.0.1:{port}/")
    print(f"   RSS Feed: http://127.0.0.1:{port}/feed")
    print(f"   健康检查: http://127.0.0.1:{port}/health")
    print(f"   Feed 文件: {feed_path or RSSFeedHandler.DEFAULT_FEED_PATH}")
    if db_path:
        print(f"   数据库: {db_path}")
        print(f"   API 端点:")
        print(f"     - GET /api/stats     综合统计")
        print(f"     - GET /api/history   爬取历史")
        print(f"     - GET /api/articles  文章列表")
        print(f"     - GET /api/failures  失败记录")
    print(f"{'=' * 60}")
    print("按 Ctrl+C 停止服务器")
    print(f"{'=' * 60}\n")

    try:
        if block:
            server.serve_forever()
        else:
            import threading
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
    except KeyboardInterrupt:
        print("\n\n[中断] 正在停止服务器...")
        server.shutdown()
        print("✅ 服务器已停止")

    return server
