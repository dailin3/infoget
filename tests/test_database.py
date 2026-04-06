"""
数据库模块单元测试
-----------------
测试 scraper.database.InfoGetDB 类的所有公共方法。

覆盖场景：
- 表创建验证
- 文章 CRUD 操作
- 爬取记录管理
- 失败记录追踪
- 统计信息查询
- 多线程并发安全
"""

import threading

import pytest

from scraper.database import InfoGetDB


class TestInitAndTables:
    """数据库初始化和表结构测试"""

    def test_init_creates_tables(self, tmp_db):
        """初始化后三张表都存在"""
        conn = tmp_db._get_connection()
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN (?, ?, ?)",
            ("articles", "crawl_records", "crawl_failures"),
        )
        table_names = {row[0] for row in cursor.fetchall()}
        assert table_names == {"articles", "crawl_records", "crawl_failures"}


class TestArticleOperations:
    """文章操作测试"""

    def test_upsert_article_new(self, tmp_db, sample_article_dict):
        """插入新文章返回 'new'"""
        result = tmp_db.upsert_article(sample_article_dict)
        assert result == "new"

    def test_upsert_article_exists(self, tmp_db, sample_article_dict):
        """相同内容文章已存在返回 'exists'"""
        # 首次插入
        tmp_db.upsert_article(sample_article_dict)
        # 再次插入相同内容
        result = tmp_db.upsert_article(sample_article_dict)
        assert result == "exists"

    def test_upsert_article_updated(self, tmp_db, sample_article_dict):
        """内容变化后更新返回 'updated'"""
        # 首次插入
        tmp_db.upsert_article(sample_article_dict)
        # 修改内容后更新
        updated_article = sample_article_dict.copy()
        updated_article["title"] = "更新后的标题"
        result = tmp_db.upsert_article(updated_article)
        assert result == "updated"

    def test_article_exists(self, tmp_db, sample_article_dict):
        """检查文章是否存在"""
        url = sample_article_dict["url"]
        # 初始不存在
        assert tmp_db.article_exists(url) is False
        # 插入后存在
        tmp_db.upsert_article(sample_article_dict)
        assert tmp_db.article_exists(url) is True

    def test_get_article(self, tmp_db, sample_article_dict):
        """根据 URL 获取文章"""
        tmp_db.upsert_article(sample_article_dict)
        article = tmp_db.get_article(sample_article_dict["url"])
        assert article is not None
        assert article["title"] == sample_article_dict["title"]
        assert article["url"] == sample_article_dict["url"]

    def test_get_article_not_found(self, tmp_db):
        """获取不存在的文章返回 None"""
        article = tmp_db.get_article("https://nonexistent.url/")
        assert article is None

    def test_get_all_articles(self, tmp_db):
        """获取所有文章，按日期排序"""
        # 插入多篇文章
        articles = [
            {"url": "https://example.com/1/", "title": "Article 1", "pub_date": "2025-01-01", "author": "", "summary": ""},
            {"url": "https://example.com/2/", "title": "Article 2", "pub_date": "2025-03-01", "author": "", "summary": ""},
            {"url": "https://example.com/3/", "title": "Article 3", "pub_date": "2025-02-01", "author": "", "summary": ""},
        ]
        for article in articles:
            tmp_db.upsert_article(article)

        # 默认按 pub_date DESC 排序
        result = tmp_db.get_all_articles()
        assert len(result) == 3
        assert result[0]["title"] == "Article 2"  # 3月
        assert result[1]["title"] == "Article 3"  # 2月
        assert result[2]["title"] == "Article 1"  # 1月

    def test_get_all_articles_empty(self, tmp_db):
        """空数据库获取文章返回空列表"""
        result = tmp_db.get_all_articles()
        assert result == []

    def test_get_article_count(self, tmp_db):
        """获取文章总数"""
        assert tmp_db.get_article_count() == 0
        tmp_db.upsert_article({
            "url": "https://example.com/1/", "title": "A1", "pub_date": "", "author": "", "summary": ""
        })
        assert tmp_db.get_article_count() == 1
        tmp_db.upsert_article({
            "url": "https://example.com/2/", "title": "A2", "pub_date": "", "author": "", "summary": ""
        })
        assert tmp_db.get_article_count() == 2

    def test_delete_article(self, tmp_db, sample_article_dict):
        """删除文章"""
        tmp_db.upsert_article(sample_article_dict)
        assert tmp_db.delete_article(sample_article_dict["url"]) is True
        assert tmp_db.get_article(sample_article_dict["url"]) is None

    def test_delete_article_not_found(self, tmp_db):
        """删除不存在的文章返回 False"""
        assert tmp_db.delete_article("https://nonexistent.url/") is False


class TestCrawlRecords:
    """爬取记录测试"""

    def test_begin_crawl(self, tmp_db):
        """开始爬取返回记录 ID"""
        crawl_id = tmp_db.begin_crawl(mode="quick")
        assert crawl_id is not None
        assert isinstance(crawl_id, int)

    def test_begin_crawl_creates_record(self, tmp_db):
        """开始爬取创建 running 状态记录"""
        crawl_id = tmp_db.begin_crawl(mode="full")
        record = tmp_db._execute(
            "SELECT * FROM crawl_records WHERE id = ?",
            (crawl_id,),
            fetch_one=True,
        )
        assert record["status"] == "running"
        assert record["mode"] == "full"

    def test_finish_crawl(self, tmp_db):
        """完成爬取更新状态"""
        crawl_id = tmp_db.begin_crawl(mode="quick")
        tmp_db.finish_crawl(crawl_id, status="success", duration=10.5)
        record = tmp_db._execute(
            "SELECT * FROM crawl_records WHERE id = ?",
            (crawl_id,),
            fetch_one=True,
        )
        assert record["status"] == "success"
        assert record["duration_seconds"] == 10.5

    def test_begin_and_finish_crawl(self, tmp_db):
        """完整流程：开始和完成爬取"""
        crawl_id = tmp_db.begin_crawl(mode="full")
        assert crawl_id > 0
        tmp_db.finish_crawl(crawl_id, status="success", duration=30.0)
        record = tmp_db._execute(
            "SELECT * FROM crawl_records WHERE id = ?",
            (crawl_id,),
            fetch_one=True,
        )
        assert record["status"] == "success"
        assert record["mode"] == "full"
        assert record["duration_seconds"] == 30.0

    def test_update_crawl_stats(self, tmp_db):
        """更新爬取统计"""
        crawl_id = tmp_db.begin_crawl(mode="quick")
        tmp_db.update_crawl_stats(
            crawl_id,
            total_found=100,
            new_count=20,
            updated_count=5,
            failed_count=3,
            exists_count=72,
        )
        record = tmp_db._execute(
            "SELECT * FROM crawl_records WHERE id = ?",
            (crawl_id,),
            fetch_one=True,
        )
        assert record["total_found"] == 100
        assert record["new_count"] == 20
        assert record["updated_count"] == 5
        assert record["failed_count"] == 3
        assert record["exists_count"] == 72

    def test_update_crawl_stats_empty(self, tmp_db):
        """不传参数时不报错"""
        crawl_id = tmp_db.begin_crawl()
        tmp_db.update_crawl_stats(crawl_id)  # 应正常执行不抛异常

    def test_get_crawl_history(self, tmp_db):
        """获取爬取历史"""
        # 创建多条爬取记录
        for i in range(5):
            cid = tmp_db.begin_crawl(mode="quick")
            tmp_db.finish_crawl(cid, status="success", duration=float(i))

        history = tmp_db.get_crawl_history()
        assert len(history) == 5
        # 默认限制 20 条
        history_limited = tmp_db.get_crawl_history(limit=2)
        assert len(history_limited) == 2

    def test_get_latest_crawl(self, tmp_db):
        """获取最近一次爬取记录"""
        # 无记录时
        assert tmp_db.get_latest_crawl() is None
        # 有记录时
        cid1 = tmp_db.begin_crawl()
        cid2 = tmp_db.begin_crawl()
        latest = tmp_db.get_latest_crawl()
        assert latest is not None
        assert latest["id"] == cid2


class TestFailureRecords:
    """失败记录测试"""

    def test_add_and_get_failure(self, tmp_db):
        """添加和获取失败记录"""
        crawl_id = tmp_db.begin_crawl()
        tmp_db.add_failure("https://example.com/failed/", "Connection timeout", crawl_id)
        failures = tmp_db.get_failures()
        assert len(failures) == 1
        assert failures[0]["url"] == "https://example.com/failed/"
        assert "Connection timeout" in failures[0]["error_message"]

    def test_get_failures_empty(self, tmp_db):
        """无失败记录时返回空列表"""
        failures = tmp_db.get_failures()
        assert failures == []

    def test_get_failures_with_limit(self, tmp_db):
        """获取失败记录限制条数"""
        crawl_id = tmp_db.begin_crawl()
        for i in range(10):
            tmp_db.add_failure(f"https://example.com/{i}/", f"Error {i}", crawl_id)
        failures = tmp_db.get_failures(limit=3)
        assert len(failures) == 3


class TestStats:
    """统计信息测试"""

    def test_get_stats(self, tmp_db, sample_article_dict):
        """获取综合统计"""
        # 插入文章
        tmp_db.upsert_article(sample_article_dict)
        # 创建爬取记录
        crawl_id = tmp_db.begin_crawl(mode="full")
        tmp_db.finish_crawl(crawl_id, status="success", duration=10.0)
        # 添加失败记录
        tmp_db.add_failure("https://example.com/bad/", "404", crawl_id)

        stats = tmp_db.get_stats()
        assert stats["total_articles"] == 1
        assert stats["total_crawls"] == 1
        assert stats["successful_crawls"] == 1
        assert stats["failed_crawls"] == 0
        assert stats["total_failures"] == 1
        assert stats["last_crawl"] is not None

    def test_get_stats_empty(self, tmp_db):
        """空数据库获取统计"""
        stats = tmp_db.get_stats()
        assert stats["total_articles"] == 0
        assert stats["total_crawls"] == 0
        # SUM() 在无记录时返回 None，代码中用 .get(key, 0) 兜底
        assert stats["successful_crawls"] in (0, None)
        assert stats["failed_crawls"] in (0, None)
        assert stats["total_failures"] == 0
        assert stats["last_crawl"] is None


class TestConcurrency:
    """线程安全测试"""

    def test_thread_safety(self, tmp_db):
        """多线程并发写入不崩溃"""
        errors = []
        success_count = [0]
        lock = threading.Lock()

        def worker(thread_id):
            try:
                article = {
                    "url": f"https://example.com/thread-{thread_id}/",
                    "title": f"Thread {thread_id} Article",
                    "pub_date": "2025-01-01",
                    "author": f"Author {thread_id}",
                    "summary": f"Summary for thread {thread_id}",
                }
                tmp_db.upsert_article(article)
                with lock:
                    success_count[0] += 1
            except Exception as e:
                with lock:
                    errors.append(str(e))

        # 创建 10 个线程并发写入
        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 验证结果
        assert len(errors) == 0, f"并发写入发生错误: {errors}"
        assert success_count[0] == 10
        assert tmp_db.get_article_count() == 10

    def test_thread_safety_mixed_operations(self, tmp_db):
        """多线程混合操作（读写混合）"""
        errors = []
        barrier = threading.Barrier(5)

        def writer(thread_id):
            try:
                barrier.wait(timeout=5)
                article = {
                    "url": f"https://example.com/mixed-{thread_id}/",
                    "title": f"Mixed {thread_id}",
                    "pub_date": "2025-01-01",
                    "author": "",
                    "summary": "",
                }
                tmp_db.upsert_article(article)
            except Exception as e:
                errors.append(f"Writer {thread_id}: {e}")

        def reader(thread_id):
            try:
                barrier.wait(timeout=5)
                tmp_db.get_all_articles()
                tmp_db.get_article_count()
                tmp_db.get_stats()
            except Exception as e:
                errors.append(f"Reader {thread_id}: {e}")

        threads = []
        # 3 个写线程 + 2 个读线程
        for i in range(3):
            threads.append(threading.Thread(target=writer, args=(i,)))
        for i in range(2):
            threads.append(threading.Thread(target=reader, args=(i,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"混合操作发生错误: {errors}"


class TestEdgeCases:
    """边界情况测试"""

    def test_upsert_article_missing_fields(self, tmp_db):
        """插入缺少字段的文章字典不崩溃"""
        # 只提供必要字段
        result = tmp_db.upsert_article({"url": "https://example.com/minimal/", "title": "Minimal"})
        assert result == "new"

    def test_upsert_article_empty_values(self, tmp_db):
        """插入空值字段不崩溃"""
        article = {
            "url": "https://example.com/empty/",
            "title": "",
            "pub_date": "",
            "author": "",
            "summary": "",
        }
        result = tmp_db.upsert_article(article)
        assert result == "new"

    def test_sql_injection_prevention(self, tmp_db):
        """SQL 注入防护验证"""
        malicious_url = "'; DROP TABLE articles; --"
        tmp_db.upsert_article({
            "url": malicious_url,
            "title": "Malicious",
            "pub_date": "",
            "author": "",
            "summary": "",
        })
        # 表应该还存在
        assert tmp_db.article_exists(malicious_url) is True
        assert tmp_db.get_article_count() == 1
