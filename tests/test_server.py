"""
HTTP 服务器单元测试
------------------
测试 scraper.server.RSSFeedHandler 的各个端点。

使用 unittest.mock 模拟请求/响应，不发真实网络请求。

覆盖端点：
- GET /health
- GET /feed
- GET /
- GET /api/stats
- GET /api/history
- GET /api/articles
- GET /api/failures
- GET /unknown (404)
"""

import io
import json
import os
from http.server import HTTPServer
from unittest.mock import MagicMock, patch

import pytest

from scraper.database import InfoGetDB
from scraper.server import RSSFeedHandler


class MockConnection:
    """模拟 HTTP 连接对象"""

    def __init__(self):
        self.request = MagicMock()
        self.client_address = ("127.0.0.1", 12345)


class MockServer:
    """模拟 HTTP 服务器对象"""

    def __init__(self):
        self.server_address = ("127.0.0.1", 8080)
        self.request_log = MagicMock()


def create_handler_instance(
    request_line="GET / HTTP/1.1",
    feed_path=None,
    db_path=None,
    feed_content=None,
):
    """
    创建 RSSFeedHandler 实例（带模拟的请求/响应）

    参数:
        request_line: 请求行字符串
        feed_path: RSS 文件路径
        db_path: 数据库路径
        feed_content: RSS 文件内容（如果提供则模拟文件存在）

    返回:
        配置好的 handler 实例，带有模拟的 wfile 和 rfile
    """
    # 解析请求行
    parts = request_line.split()
    method = parts[0]
    path = parts[1] if len(parts) > 1 else "/"

    # 创建模拟连接
    mock_conn = MockConnection()
    mock_conn.request.makefile.return_value = io.BytesIO(request_line.encode())

    # 创建模拟 server
    mock_server = MockServer()

    # 创建 wfile（写入响应）
    wfile = io.BytesIO()

    # 创建 rfile（读取请求）
    rfile = io.BytesIO(request_line.encode())

    # 使用 patch 避免真实的 socket 操作
    with patch.object(RSSFeedHandler, "__init__", lambda self, *a, **kw: None):
        handler = RSSFeedHandler()
        handler.request = mock_conn.request
        handler.client_address = mock_conn.client_address
        handler.server = mock_server
        handler.wfile = wfile
        handler.rfile = rfile
        handler.command = method
        handler.path = path
        handler.requestline = request_line  # 日志需要
        handler.request_version = "HTTP/1.1"
        handler.protocol_version = "HTTP/1.0"
        handler.headers = MagicMock()
        handler.headers.get.return_value = "127.0.0.1:8080"

        # 设置 feed_path
        if feed_path:
            handler.feed_path = os.path.abspath(feed_path)
        else:
            handler.feed_path = "/tmp/test_feed.xml"

        # 初始化数据库
        handler.db = None
        if db_path:
            handler.db = InfoGetDB(db_path)

    return handler


class TestHealthEndpoint:
    """健康检查端点测试"""

    def test_serve_health(self):
        """/health 返回 {"status": "ok"}"""
        handler = create_handler_instance("GET /health HTTP/1.1")

        handler._serve_health()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        # 查找 JSON body（在 headers 之后）
        body = response.split("\r\n\r\n", 1)[-1] if "\r\n\r\n" in response else response
        data = json.loads(body)
        assert data == {"status": "ok"}


class TestFeedEndpoint:
    """RSS Feed 端点测试"""

    def test_serve_feed_exists(self, tmp_path, sample_rss_xml):
        """/feed 返回 200 和 XML 内容"""
        feed_file = tmp_path / "feed.xml"
        feed_file.write_text(sample_rss_xml, encoding="utf-8")

        handler = create_handler_instance(
            "GET /feed HTTP/1.1",
            feed_path=str(feed_file),
        )

        handler._serve_feed()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "HTTP/1.0 200" in response
        assert "application/rss+xml" in response
        assert "<?xml" in response

    def test_serve_feed_not_exists(self):
        """/feed 文件不存在返回 404"""
        handler = create_handler_instance(
            "GET /feed HTTP/1.1",
            feed_path="/nonexistent/path/feed.xml",
        )

        handler._serve_feed()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "404" in response


class TestIndexEndpoint:
    """首页端点测试"""

    def test_serve_index_with_feed(self, tmp_path, sample_rss_xml):
        """/ 返回 HTML 页面（有 RSS 文件时）"""
        feed_file = tmp_path / "feed.xml"
        feed_file.write_text(sample_rss_xml, encoding="utf-8")

        handler = create_handler_instance(
            "GET / HTTP/1.1",
            feed_path=str(feed_file),
        )

        handler._serve_index()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "HTTP/1.0 200" in response
        assert "text/html" in response
        assert "<!DOCTYPE html>" in response

    def test_serve_index_no_feed(self):
        """/ 返回 404（无 RSS 文件时）"""
        handler = create_handler_instance(
            "GET / HTTP/1.1",
            feed_path="/nonexistent/feed.xml",
        )

        handler._serve_index()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        # 应该返回 404
        assert "404" in response


class TestNotFoundEndpoint:
    """404 端点测试"""

    def test_serve_404(self):
        """未知路径返回 404"""
        handler = create_handler_instance("GET /unknown/path HTTP/1.1")

        handler._serve_404()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "404" in response
        assert "页面未找到" in response


class TestApiEndpointsWithDB:
    """API 端点测试（带数据库）"""

    @pytest.fixture
    def handler_with_db(self, tmp_path, tmp_db):
        """创建带数据库的 handler"""
        db_path = str(tmp_path / "api_test.db")
        # 复用 tmp_db 的数据（复制到新路径）
        import shutil
        shutil.copy(tmp_db.db_path, db_path)

        handler = create_handler_instance(
            "GET / HTTP/1.1",
            db_path=db_path,
        )
        return handler

    def test_api_stats(self, handler_with_db, tmp_db):
        """/api/stats 返回统计信息"""
        # 先添加一些数据
        tmp_db.upsert_article({
            "url": "https://example.com/stats-test/",
            "title": "Stats Test",
            "pub_date": "2025-01-01",
            "author": "",
            "summary": "",
        })
        cid = tmp_db.begin_crawl()
        tmp_db.finish_crawl(cid, status="success")

        handler = create_handler_instance(
            "GET /api/stats HTTP/1.1",
            db_path=tmp_db.db_path,
        )

        handler._serve_api_stats()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        body = response.split("\r\n\r\n", 1)[-1]
        data = json.loads(body)

        assert data["success"] is True
        assert "total_articles" in data["data"]
        assert "total_crawls" in data["data"]

    def test_api_history(self, handler_with_db, tmp_db):
        """/api/history 返回爬取历史列表"""
        # 添加爬取记录
        for i in range(3):
            cid = tmp_db.begin_crawl(mode="quick")
            tmp_db.finish_crawl(cid, status="success", duration=float(i))

        handler = create_handler_instance(
            "GET /api/history HTTP/1.1",
            db_path=tmp_db.db_path,
        )

        handler._serve_api_history()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        body = response.split("\r\n\r\n", 1)[-1]
        data = json.loads(body)

        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert data["count"] == 3

    def test_api_articles(self, handler_with_db, tmp_db):
        """/api/articles 返回文章列表（支持分页）"""
        # 添加文章
        for i in range(5):
            tmp_db.upsert_article({
                "url": f"https://example.com/article-{i}/",
                "title": f"Article {i}",
                "pub_date": f"2025-01-{i+1:02d}",
                "author": "",
                "summary": f"Summary {i}",
            })

        handler = create_handler_instance(
            "GET /api/articles HTTP/1.1",
            db_path=tmp_db.db_path,
        )

        # 模拟 parsed_path
        from urllib.parse import urlparse
        parsed_path = urlparse("/api/articles?page=1&page_size=2")

        handler._serve_api_articles(parsed_path)

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        body = response.split("\r\n\r\n", 1)[-1]
        data = json.loads(body)

        assert data["success"] is True
        assert "articles" in data["data"]
        assert data["data"]["total"] == 5
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 2
        # 分页应该只返回 2 条
        assert len(data["data"]["articles"]) == 2

    def test_api_failures(self, handler_with_db, tmp_db):
        """/api/failures 返回失败记录"""
        cid = tmp_db.begin_crawl()
        tmp_db.add_failure("https://example.com/failed/", "Timeout", cid)

        handler = create_handler_instance(
            "GET /api/failures HTTP/1.1",
            db_path=tmp_db.db_path,
        )

        handler._serve_api_failures()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        body = response.split("\r\n\r\n", 1)[-1]
        data = json.loads(body)

        assert data["success"] is True
        assert isinstance(data["data"], list)
        assert data["count"] == 1


class TestApiEndpointsWithoutDB:
    """API 端点测试（无数据库）"""

    def test_api_stats_no_db(self):
        """无数据库时 /api/stats 返回 503"""
        handler = create_handler_instance("GET /api/stats HTTP/1.1")
        handler.db = None

        handler._serve_api_stats()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "503" in response

    def test_api_history_no_db(self):
        """无数据库时 /api/history 返回 503"""
        handler = create_handler_instance("GET /api/history HTTP/1.1")
        handler.db = None

        handler._serve_api_history()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "503" in response

    def test_api_articles_no_db(self):
        """无数据库时 /api/articles 返回 503"""
        handler = create_handler_instance("GET /api/articles HTTP/1.1")
        handler.db = None

        from urllib.parse import urlparse
        parsed_path = urlparse("/api/articles")

        handler._serve_api_articles(parsed_path)

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "503" in response

    def test_api_failures_no_db(self):
        """无数据库时 /api/failures 返回 503"""
        handler = create_handler_instance("GET /api/failures HTTP/1.1")
        handler.db = None

        handler._serve_api_failures()

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "503" in response


class TestRSSExtraction:
    """RSS 解析测试"""

    def test_extract_articles_from_rss(self, sample_rss_xml):
        """从 RSS XML 提取文章信息"""
        handler = create_handler_instance("GET / HTTP/1.1")
        articles = handler._extract_articles_from_rss(sample_rss_xml)

        assert len(articles) == 2
        assert articles[0]["title"] == "Qwen3 技术报告"
        assert "qwen3-tech-report" in articles[0]["link"]
        assert articles[0]["author"] == "Qwen Team"

    def test_extract_articles_from_rss_empty(self):
        """空 RSS 返回空列表"""
        handler = create_handler_instance("GET / HTTP/1.1")
        empty_rss = '''<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <title>Empty</title>
  </channel>
</rss>'''
        articles = handler._extract_articles_from_rss(empty_rss)
        assert articles == []


class TestErrorPages:
    """错误页面测试"""

    def test_build_error_html(self):
        """构建错误页面 HTML"""
        handler = create_handler_instance("GET / HTTP/1.1")
        html = handler._build_error_html("测试错误", "错误详情")

        assert "测试错误" in html
        assert "错误详情" in html
        assert "<!DOCTYPE html>" in html

    def test_build_error_html_escapes(self):
        """错误页面转义特殊字符"""
        handler = create_handler_instance("GET / HTTP/1.1")
        html = handler._build_error_html("<script>", "alert('xss')")

        # 原始 <script> 标签应被转义，不应以原始形式出现
        assert "&lt;script&gt;" in html
        # alert 中的引号也应被转义
        assert "alert(" in html


class TestSendHelpers:
    """响应发送辅助方法测试"""

    def test_send_json(self):
        """_send_json 发送正确 JSON"""
        handler = create_handler_instance("GET / HTTP/1.1")
        handler._send_json({"key": "value"}, status=201)

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "HTTP/1.0 201" in response
        assert "application/json" in response
        assert '{"key": "value"}' in response

    def test_send_html(self):
        """_send_html 发送正确 HTML"""
        handler = create_handler_instance("GET / HTTP/1.1")
        handler._send_html("<h1>Hello</h1>", status=200)

        handler.wfile.seek(0)
        response = handler.wfile.read().decode()
        assert "HTTP/1.0 200" in response
        assert "text/html" in response
        assert "<h1>Hello</h1>" in response
