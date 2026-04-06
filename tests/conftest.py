"""
pytest 配置和共享 fixture
------------------------
提供所有测试模块共用的 fixture，包括：
- 临时数据库
- 模拟文章数据
- 模拟 HTML 页面
- 模拟 RSS XML
"""

import os
import sys
import tempfile

import pytest

# 将项目根目录添加到 Python 路径，确保可以导入 scraper 模块
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@pytest.fixture
def tmp_db(tmp_path):
    """
    临时 SQLite 数据库 fixture

    每个测试使用独立的临时数据库文件，测试结束后自动清理。

    返回:
        InfoGetDB 实例
    """
    from scraper.database import InfoGetDB

    db_file = tmp_path / "test_infoget.db"
    db = InfoGetDB(str(db_file))
    yield db
    db.close()


@pytest.fixture
def sample_articles():
    """
    模拟文章数据列表

    返回:
        包含 3 篇模拟文章的列表（Article 对象）
    """
    from scraper.scraper import Article

    return [
        Article(
            title="Qwen3 技术报告",
            url="https://qwenlm.github.io/qwen-code-docs/zh/blog/qwen3-tech-report/",
            pub_date="2025-03-15T10:00:00",
            author="Qwen Team",
            summary="Qwen3 模型的技术报告，介绍了架构改进和性能提升。",
        ),
        Article(
            title="Qwen Code 使用指南",
            url="https://qwenlm.github.io/qwen-code-docs/zh/blog/qwen-code-guide/",
            pub_date="2025-02-20T14:30:00",
            author="DevRel Team",
            summary="如何使用 Qwen Code 提高开发效率。",
        ),
        Article(
            title="多模态理解能力更新",
            url="https://qwenlm.github.io/qwen-code-docs/zh/blog/multimodal-update/",
            pub_date="2025-01-10T09:00:00",
            author="Research Team",
            summary="Qwen 在多模态理解方面的最新进展。",
        ),
    ]


@pytest.fixture
def sample_article_dict():
    """
    模拟文章数据字典

    返回:
        单篇文章的字典数据
    """
    return {
        "url": "https://qwenlm.github.io/qwen-code-docs/zh/blog/test-article/",
        "title": "测试文章",
        "pub_date": "2025-04-01T12:00:00",
        "author": "Test Author",
        "summary": "这是一篇用于测试的文章。",
    }


@pytest.fixture
def sample_html():
    """
    模拟博客列表页 HTML

    包含 Nextra 框架典型的文章卡片结构。

    返回:
        HTML 字符串
    """
    return """<!DOCTYPE html>
<html>
<head><title>Qwen Code Docs Blog</title></head>
<body>
<main>
  <div>
    <div>
      <a class="group flex items-start gap-6" href="/qwen-code-docs/zh/blog/article-01/">
        <div class="hidden sm:flex">
          <span>15</span>
          <span>3月</span>
        </div>
        <div>
          <div>技术</div>
          <h3>Qwen3 技术报告</h3>
          <p>Qwen3 模型的技术报告，介绍了架构改进和性能提升。</p>
          <div>
            <svg class="lucide-user" width="16" height="16"><use href="#user-icon"/></svg>
            <span>Qwen Team</span>
          </div>
        </div>
      </a>
      <a class="group flex items-start gap-6" href="/qwen-code-docs/zh/blog/article-02/">
        <div class="hidden sm:flex">
          <span>20</span>
          <span>2月</span>
        </div>
        <div>
          <div>教程</div>
          <h3>Qwen Code 使用指南</h3>
          <p>如何使用 Qwen Code 提高开发效率。</p>
          <div>
            <svg class="lucide-user" width="16" height="16"><use href="#user-icon"/></svg>
            <span>DevRel Team</span>
          </div>
        </div>
      </a>
      <a class="group flex items-start gap-6" href="/qwen-code-docs/zh/blog/article-03/">
        <div class="hidden sm:flex">
          <span>10</span>
          <span>1月</span>
        </div>
        <div>
          <div>研究</div>
          <h3>多模态理解能力更新</h3>
          <p>Qwen 在多模态理解方面的最新进展。</p>
          <div>
            <svg class="lucide-user" width="16" height="16"><use href="#user-icon"/></svg>
            <span>Research Team</span>
          </div>
        </div>
      </a>
    </div>
  </div>
</main>
</body>
</html>"""


@pytest.fixture
def sample_html_empty():
    """
    模拟空的博客列表页 HTML

    返回:
        HTML 字符串（无文章内容）
    """
    return """<!DOCTYPE html>
<html>
<head><title>Qwen Code Docs Blog</title></head>
<body>
<main>
  <div><p>暂无文章</p></div>
</main>
</body>
</html>"""


@pytest.fixture
def sample_rss_xml():
    """
    标准 RSS 2.0 XML 字符串

    返回:
        RSS XML 字符串
    """
    return '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:dc="http://purl.org/dc/elements/1.1/">
  <channel>
    <title>Qwen Code Docs 博客</title>
    <link>https://qwenlm.github.io/qwen-code-docs/zh/blog/</link>
    <description>Qwen Code 官方文档博客文章</description>
    <language>zh-CN</language>
    <lastBuildDate>Mon, 06 Apr 2026 12:00:00 GMT</lastBuildDate>
    <atom:link href="https://qwenlm.github.io/qwen-code-docs/zh/blog/" rel="self" type="application/rss+xml"/>
    <generator>Qwen Blog RSS Generator (Python)</generator>
    <item>
      <title>Qwen3 技术报告</title>
      <link>https://qwenlm.github.io/qwen-code-docs/zh/blog/qwen3-tech-report/</link>
      <description>Qwen3 模型的技术报告，介绍了架构改进和性能提升。</description>
      <dc:creator>Qwen Team</dc:creator>
      <pubDate>Sat, 15 Mar 2025 10:00:00 GMT</pubDate>
      <guid isPermaLink="true">https://qwenlm.github.io/qwen-code-docs/zh/blog/qwen3-tech-report/</guid>
    </item>
    <item>
      <title>Qwen Code 使用指南</title>
      <link>https://qwenlm.github.io/qwen-code-docs/zh/blog/qwen-code-guide/</link>
      <description>如何使用 Qwen Code 提高开发效率。</description>
      <dc:creator>DevRel Team</dc:creator>
      <pubDate>Thu, 20 Feb 2025 14:30:00 GMT</pubDate>
      <guid isPermaLink="true">https://qwenlm.github.io/qwen-code-docs/zh/blog/qwen-code-guide/</guid>
    </item>
  </channel>
</rss>'''


@pytest.fixture
def sample_feed_xml_path(tmp_path, sample_rss_xml):
    """
    临时 RSS 文件 fixture

    返回:
        RSS 文件的绝对路径
    """
    feed_file = tmp_path / "feed.xml"
    feed_file.write_text(sample_rss_xml, encoding="utf-8")
    return str(feed_file)
