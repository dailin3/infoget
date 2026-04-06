"""
RSS 生成器单元测试
-----------------
测试 scraper.rss_generator.RSSGenerator 类的所有公共方法。

覆盖场景：
- 基本 RSS 生成
- RSS 版本和频道元素
- 文章条目元素
- 空列表生成
- 文件保存
- XML 特殊字符转义
- feedgen 不可用时的手动拼接降级
"""

import os
from unittest.mock import patch

import pytest

from scraper.rss_generator import RSSGenerator
from scraper.scraper import Article


class TestBasicGeneration:
    """基本生成功能测试"""

    def test_generate_basic(self, sample_articles):
        """基本 RSS 生成"""
        generator = RSSGenerator()
        rss_content = generator.generate(sample_articles)

        assert rss_content is not None
        assert isinstance(rss_content, str)
        assert len(rss_content) > 0
        assert "<?xml" in rss_content
        assert "<rss" in rss_content

    def test_rss_version(self, sample_articles):
        """输出包含 version="2.0" """
        generator = RSSGenerator()
        rss_content = generator.generate(sample_articles)
        assert 'version="2.0"' in rss_content

    def test_channel_elements(self, sample_articles):
        """包含 title、link、description、language"""
        generator = RSSGenerator(
            title="自定义标题",
            link="https://example.com/blog/",
            description="自定义描述",
            language="en-US",
        )
        rss_content = generator.generate(sample_articles)

        assert "<title>自定义标题</title>" in rss_content
        assert "<link>https://example.com/blog/</link>" in rss_content
        assert "<description>自定义描述</description>" in rss_content
        assert "<language>en-US</language>" in rss_content

    def test_item_elements(self, sample_articles):
        """每篇文章包含 title、link、description、pubDate、guid"""
        generator = RSSGenerator()
        rss_content = generator.generate(sample_articles)

        for article in sample_articles:
            # 验证每篇文章的元素存在
            assert f"<title>{article.title}</title>" in rss_content
            assert f"<link>{article.url}</link>" in rss_content
            # guid 应该包含 URL
            assert article.url in rss_content


class TestEmptyGeneration:
    """空列表生成测试"""

    def test_generate_empty(self):
        """空文章列表也能生成合法 RSS"""
        generator = RSSGenerator()
        rss_content = generator.generate([])

        assert "<?xml" in rss_content
        assert 'version="2.0"' in rss_content
        assert "<channel>" in rss_content
        assert "</channel>" in rss_content
        assert "</rss>" in rss_content
        # 不应该有 item 元素
        assert "<item>" not in rss_content


class TestFileSave:
    """文件保存测试"""

    def test_save_to_file(self, sample_articles, tmp_path):
        """保存到文件并验证内容"""
        generator = RSSGenerator()
        rss_content = generator.generate(sample_articles)

        output_file = str(tmp_path / "test_feed.xml")
        result_path = RSSGenerator.save_to_file(rss_content, output_file)

        # 验证文件存在
        assert os.path.exists(output_file)
        # 验证返回绝对路径
        assert os.path.isabs(result_path)
        # 验证内容正确
        with open(output_file, "r", encoding="utf-8") as f:
            saved_content = f.read()
        assert saved_content == rss_content

    def test_save_to_file_creates_directory(self, tmp_path):
        """保存文件时自动创建目录"""
        generator = RSSGenerator()
        rss_content = generator.generate([])

        nested_dir = tmp_path / "nested" / "dir"
        output_file = str(nested_dir / "feed.xml")

        result_path = RSSGenerator.save_to_file(rss_content, output_file)
        assert os.path.exists(output_file)


class TestXMLEscaping:
    """XML 转义测试"""

    def test_xml_escaping(self):
        """特殊字符（&, <, >）被正确转义"""
        articles = [
            Article(
                title="使用 C++ & Rust 开发",
                url="https://example.com/post-1/",
                summary="比较 <C++> 和 >Rust< 的优劣",
            ),
        ]
        generator = RSSGenerator()
        rss_content = generator.generate(articles)

        # & 应该被转义为 &amp;
        assert "&amp;" in rss_content
        # < 和 > 应该被转义（不会以原始形式出现在文本内容中）
        assert "C++ &amp; Rust" in rss_content


class TestManualRSSFallback:
    """手动拼接降级测试"""

    def test_manual_rss_fallback(self, sample_articles):
        """模拟 feedgen 不可用时的手动拼接"""
        generator = RSSGenerator()

        # 模拟 feedgen 导入失败
        with patch.object(generator, "_try_feedgen", return_value=None):
            rss_content = generator._manual_rss(sample_articles)

        assert rss_content is not None
        assert 'version="2.0"' in rss_content
        assert "<channel>" in rss_content
        # 验证文章条目存在
        for article in sample_articles:
            assert f"<title>{article.title}</title>" in rss_content
            assert f"<link>{article.url}</link>" in rss_content
            assert f'<guid isPermaLink="true">{article.url}</guid>' in rss_content

    def test_manual_rss_empty_list(self):
        """手动拼接空列表"""
        generator = RSSGenerator()
        rss_content = generator._manual_rss([])

        assert "<?xml" in rss_content
        assert 'version="2.0"' in rss_content
        assert "<item>" not in rss_content

    def test_manual_rss_with_author(self):
        """手动拼接包含作者的文章"""
        articles = [
            Article(
                title="Author Test",
                url="https://example.com/author/",
                author="Test Author",
                summary="Summary",
            ),
        ]
        generator = RSSGenerator()
        with patch.object(generator, "_try_feedgen", return_value=None):
            rss_content = generator._manual_rss(articles)

        assert "<dc:creator>Test Author</dc:creator>" in rss_content

    def test_manual_rss_xml_escaping(self):
        """手动拼接时特殊字符转义"""
        articles = [
            Article(
                title="A & B",
                url="https://example.com/a&b/",
                summary="Use <tag> and >other<",
            ),
        ]
        generator = RSSGenerator()
        with patch.object(generator, "_try_feedgen", return_value=None):
            rss_content = generator._manual_rss(articles)

        # URL 中的 & 也应该被转义
        assert "a&amp;b" in rss_content
        assert "A &amp; B" in rss_content


class TestEdgeCases:
    """边界情况测试"""

    def test_generate_with_custom_channel_params(self):
        """使用自定义频道参数生成"""
        generator = RSSGenerator(
            title="My Blog",
            link="https://myblog.com/",
            description="My awesome blog",
            language="en-US",
            author="John Doe",
        )
        rss_content = generator.generate([])

        assert "<title>My Blog</title>" in rss_content
        assert "<link>https://myblog.com/</link>" in rss_content
        assert "<description>My awesome blog</description>" in rss_content
        assert "<language>en-US</language>" in rss_content

    def test_generate_article_without_pub_date(self):
        """生成没有发布日期的文章"""
        articles = [
            Article(
                title="No Date",
                url="https://example.com/no-date/",
                pub_date="",
            ),
        ]
        generator = RSSGenerator()
        rss_content = generator.generate(articles)

        # 应该正常生成，不崩溃
        assert "<title>No Date</title>" in rss_content

    def test_generate_article_with_invalid_date(self):
        """生成带有无效日期格式的文章"""
        articles = [
            Article(
                title="Bad Date",
                url="https://example.com/bad-date/",
                pub_date="not-a-date",
            ),
        ]
        generator = RSSGenerator()
        # 不应该崩溃，应该优雅处理
        rss_content = generator.generate(articles)
        assert "<title>Bad Date</title>" in rss_content
