"""
爬虫模块单元测试
---------------
测试 scraper.scraper.QwenBlogScraper 类和 Article 类。

注意：本测试使用模拟 HTML，不发真实网络请求。

覆盖场景：
- 解析博客列表页提取文章
- 空页面处理
- URL 日期提取
- Article.to_dict() 序列化
"""

from bs4 import BeautifulSoup

from scraper.scraper import Article, QwenBlogScraper


class TestArticle:
    """Article 数据类测试"""

    def test_article_to_dict(self):
        """Article.to_dict() 返回正确格式"""
        article = Article(
            title="测试文章",
            url="https://example.com/test/",
            pub_date="2025-04-01T12:00:00",
            author="测试作者",
            summary="这是一篇测试文章。",
        )
        result = article.to_dict()

        assert isinstance(result, dict)
        assert result["title"] == "测试文章"
        assert result["url"] == "https://example.com/test/"
        assert result["pub_date"] == "2025-04-01T12:00:00"
        assert result["author"] == "测试作者"
        assert result["summary"] == "这是一篇测试文章。"

    def test_article_to_dict_empty_fields(self):
        """Article.to_dict() 空字段也包含在内"""
        article = Article()
        result = article.to_dict()

        assert result["title"] == ""
        assert result["url"] == ""
        assert result["pub_date"] == ""
        assert result["author"] == ""
        assert result["summary"] == ""

    def test_article_repr(self):
        """Article.__repr__() 返回调试信息"""
        article = Article(title="Test", url="https://example.com/")
        repr_str = repr(article)
        assert "Article" in repr_str
        assert "Test" in repr_str


class TestDateExtraction:
    """日期提取测试"""

    def test_extract_date_from_url_with_ymd_format(self):
        """从 URL 提取 YYYY/MM/DD 格式日期"""
        scraper = QwenBlogScraper(use_db=False)
        url = "https://qwenlm.github.io/blog/2024/01/15/some-title/"
        date = scraper._extract_date_from_url(url)
        assert date == "2024-01-15"

    def test_extract_date_from_url_with_dash_format(self):
        """从 URL 提取 YYYY-MM-DD 格式日期"""
        scraper = QwenBlogScraper(use_db=False)
        url = "https://qwenlm.github.io/blog/2024-03-20-another-title/"
        date = scraper._extract_date_from_url(url)
        assert date == "2024-03-20"

    def test_extract_date_from_url_no_date(self):
        """URL 中无日期返回空字符串"""
        scraper = QwenBlogScraper(use_db=False)
        url = "https://qwenlm.github.io/blog/some-post/"
        date = scraper._extract_date_from_url(url)
        assert date == ""

    def test_extract_date_from_url_complex_path(self):
        """复杂路径中提取日期"""
        scraper = QwenBlogScraper(use_db=False)
        url = "https://qwenlm.github.io/qwen-code-docs/zh/blog/2025/02/28/qwen-update/"
        date = scraper._extract_date_from_url(url)
        assert date == "2025-02-28"


class TestListPageParsing:
    """列表页解析测试"""

    def test_parse_list_page_extract_articles(self, sample_html):
        """解析模拟的博客列表页 HTML，提取文章"""
        scraper = QwenBlogScraper(use_db=False)
        soup = BeautifulSoup(sample_html, "lxml")
        articles = scraper._parse_list_page(soup)

        # 验证提取了 3 篇文章
        assert len(articles) == 3

        # 验证第一篇文章
        first = articles[0]
        assert "Qwen3 技术报告" in first["title"]
        assert "/blog/article-01/" in first["url"]
        assert first["author"] == "Qwen Team"
        assert "架构改进" in first["summary"]

        # 验证作者提取
        assert articles[1]["author"] == "DevRel Team"
        assert articles[2]["author"] == "Research Team"

    def test_parse_list_page_empty(self, sample_html_empty):
        """空页面不崩溃"""
        scraper = QwenBlogScraper(use_db=False)
        soup = BeautifulSoup(sample_html_empty, "lxml")
        articles = scraper._parse_list_page(soup)
        assert articles == []

    def test_parse_list_page_full_url(self):
        """文章链接是完整 URL 时正确处理"""
        html = """<!DOCTYPE html>
<html><body><main>
  <a href="https://qwenlm.github.io/blog/full-url-post/">
    <h3>Full URL Post</h3>
    <p>Summary</p>
  </a>
</main></body></html>"""
        scraper = QwenBlogScraper(use_db=False)
        soup = BeautifulSoup(html, "lxml")
        articles = scraper._parse_list_page(soup)

        assert len(articles) == 1
        assert articles[0]["url"] == "https://qwenlm.github.io/blog/full-url-post/"

    def test_parse_list_page_deduplicates(self):
        """重复链接只保留一个"""
        html = """<!DOCTYPE html>
<html><body><main>
  <a href="/blog/same-post/">
    <h3>Same Post</h3>
  </a>
  <a href="/blog/same-post/">
    <h3>Same Post</h3>
  </a>
</main></body></html>"""
        scraper = QwenBlogScraper(use_db=False)
        soup = BeautifulSoup(html, "lxml")
        articles = scraper._parse_list_page(soup)

        assert len(articles) == 1

    def test_parse_list_page_skips_invalid_links(self):
        """跳过空链接、锚点链接、外部链接"""
        html = """<!DOCTYPE html>
<html><body><main>
  <a href="">Empty</a>
  <a href="#anchor">Anchor</a>
  <a href="javascript:void(0)">JS</a>
  <a href="https://external.com/blog/post/">External</a>
  <a href="/blog/valid/">
    <h3>Valid</h3>
  </a>
</main></body></html>"""
        scraper = QwenBlogScraper(use_db=False)
        soup = BeautifulSoup(html, "lxml")
        articles = scraper._parse_list_page(soup)

        # 只有包含 /blog/ 的有效内部链接才被保留
        assert len(articles) == 1
        assert articles[0]["url"].endswith("/blog/valid/")

    def test_parse_list_page_title_fallback(self):
        """无 h3 标签时使用链接文本作为标题"""
        html = """<!DOCTYPE html>
<html><body><main>
  <a href="/blog/no-h3/">No H3 Title</a>
</main></body></html>"""
        scraper = QwenBlogScraper(use_db=False)
        soup = BeautifulSoup(html, "lxml")
        articles = scraper._parse_list_page(soup)

        assert len(articles) == 1
        assert articles[0]["title"] == "No H3 Title"


class TestScraperInit:
    """爬虫初始化测试"""

    def test_init_without_db(self):
        """禁用数据库模式初始化"""
        scraper = QwenBlogScraper(use_db=False)
        assert scraper.use_db is False
        assert scraper.db is None
        assert scraper.delay == 1.0

    def test_init_with_custom_delay(self):
        """自定义延迟"""
        scraper = QwenBlogScraper(use_db=False, delay=2.5)
        assert scraper.delay == 2.5

    def test_init_base_url(self):
        """验证基础 URL"""
        scraper = QwenBlogScraper(use_db=False)
        assert scraper.BASE_URL == "https://qwenlm.github.io"
        assert "blog" in scraper.BLOG_LIST_URL


class TestEdgeCases:
    """边界情况测试"""

    def test_parse_list_page_with_none_attributes(self):
        """页面元素属性为 None 时不崩溃"""
        html = """<!DOCTYPE html>
<html><body><main>
  <a href="/blog/test/">
    <h3>Test</h3>
    <p>Summary</p>
  </a>
</main></body></html>"""
        scraper = QwenBlogScraper(use_db=False)
        soup = BeautifulSoup(html, "lxml")
        articles = scraper._parse_list_page(soup)

        assert len(articles) == 1
