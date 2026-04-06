"""
数据库操作模块
--------------
使用 SQLite 数据库持久化爬取记录，支持增量更新和去重。

主要功能：
1. 文章记录的增删改查（URL 唯一键去重）
2. 爬取记录的统计和查询
3. 失败记录的追踪和查询

技术实现：
- 仅使用 Python 标准库 sqlite3，零额外依赖
- 线程安全：使用 check_same_thread=False 和 threading.Lock
- 容错处理：数据库损坏时自动重建
"""

import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Optional


def _iso_now() -> str:
    """
    获取当前时间的 ISO 8601 格式字符串

    返回:
        ISO 8601 格式的时间字符串，如 "2026-04-06T12:00:00"
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


class InfoGetDB:
    """
    数据库操作类
    ------------
    提供文章和爬取记录的增删改查。

    使用示例:
        db = InfoGetDB("data/infoget.db")
        db.upsert_article({"url": "...", "title": "...", ...})
        crawl_id = db.begin_crawl(mode="quick")
        # ... 爬取逻辑 ...
        db.finish_crawl(crawl_id, status="success", duration=10.5)
        stats = db.get_stats()

    线程安全:
        内部使用 threading.Lock 保证多线程安全。
    """

    # 数据库初始化 SQL
    _INIT_SQL = """
        -- 文章记录表
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            pub_date TEXT,
            author TEXT,
            summary TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        -- 爬取记录表
        CREATE TABLE IF NOT EXISTS crawl_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            crawl_time TEXT NOT NULL,
            total_found INTEGER DEFAULT 0,
            new_count INTEGER DEFAULT 0,
            updated_count INTEGER DEFAULT 0,
            failed_count INTEGER DEFAULT 0,
            duration_seconds REAL DEFAULT 0,
            mode TEXT DEFAULT 'quick',
            status TEXT DEFAULT 'success',
            error_detail TEXT
        );

        -- 失败记录表
        CREATE TABLE IF NOT EXISTS crawl_failures (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT,
            error_message TEXT NOT NULL,
            crawl_record_id INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (crawl_record_id) REFERENCES crawl_records(id)
        );

        -- 索引
        CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
        CREATE INDEX IF NOT EXISTS idx_articles_pub_date ON articles(pub_date);
        CREATE INDEX IF NOT EXISTS idx_crawl_records_time ON crawl_records(crawl_time);
    """

    def __init__(self, db_path: str = "data/infoget.db"):
        """
        初始化数据库，创建必要的表和索引

        参数:
            db_path: SQLite 数据库文件路径
        """
        # 确保数据库目录存在
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接（惰性初始化）

        使用 check_same_thread=False 允许跨线程使用连接，
        但实际写操作通过 self._lock 保证线程安全。

        返回:
            sqlite3.Connection 对象
        """
        if self._conn is None:
            try:
                self._conn = sqlite3.connect(
                    self.db_path,
                    check_same_thread=False,
                )
                # 启用外键约束
                self._conn.execute("PRAGMA foreign_keys = ON")
                # 使用 WAL 模式提高并发性能
                self._conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.Error:
                # 数据库可能损坏，尝试重建
                self._rebuild_db()
        return self._conn

    def _rebuild_db(self):
        """
        重建数据库：删除损坏的数据库文件并重新创建

        当数据库文件损坏时调用此方法。
        """
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
                print(f"[数据库] 已删除损坏的数据库文件: {self.db_path}")
        except OSError as e:
            print(f"[警告] 删除数据库文件失败: {e}")

        self._conn = None
        self._init_db()

    def _init_db(self):
        """
        初始化数据库：执行建表 SQL + 列迁移

        使用 executescript 一次执行多条 SQL 语句。
        """
        conn = self._get_connection()
        try:
            conn.executescript(self._INIT_SQL)
            # 列迁移：为旧数据库添加 exists_count 列
            try:
                conn.execute(
                    "ALTER TABLE crawl_records ADD COLUMN exists_count INTEGER DEFAULT 0"
                )
                conn.commit()
                print("[数据库] 已添加 exists_count 列")
            except sqlite3.OperationalError:
                # 列已存在，忽略错误
                pass
            conn.commit()
        except sqlite3.Error as e:
            print(f"[数据库] 初始化失败: {e}")
            raise

    def _execute(self, sql: str, params: tuple = (), fetch_one: bool = False, fetch_all: bool = False):
        """
        执行 SQL 语句的辅助方法（线程安全）

        参数:
            sql: SQL 语句
            params: SQL 参数
            fetch_one: 是否获取单行结果
            fetch_all: 是否获取所有结果

        返回:
            根据 fetch_one/fetch_all 返回不同结果
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(sql, params)
                conn.commit()

                if fetch_one:
                    # 将行对象转换为字典
                    row = cursor.fetchone()
                    if row:
                        return dict(zip([d[0] for d in cursor.description], row))
                    return None
                elif fetch_all:
                    rows = cursor.fetchall()
                    return [dict(zip([d[0] for d in cursor.description], row)) for row in rows]
                else:
                    return cursor
            except sqlite3.Error as e:
                print(f"[数据库] SQL 执行失败: {e}, SQL: {sql}")
                raise

    # =========================================================================
    # 文章操作
    # =========================================================================

    def article_exists(self, url: str) -> bool:
        """
        检查文章是否已存在于数据库中

        参数:
            url: 文章 URL

        返回:
            True 如果文章已存在，否则 False
        """
        result = self._execute(
            "SELECT 1 FROM articles WHERE url = ?",
            (url,),
            fetch_one=True,
        )
        return result is not None

    def get_article(self, url: str) -> Optional[dict]:
        """
        根据 URL 获取文章信息

        参数:
            url: 文章 URL

        返回:
            文章信息字典，如果不存在则返回 None
        """
        return self._execute(
            "SELECT * FROM articles WHERE url = ?",
            (url,),
            fetch_one=True,
        )

    def upsert_article(self, article: dict) -> str:
        """
        插入或更新文章（增量更新逻辑）

        逻辑:
            - 如果文章不存在 → 插入新记录，返回 "new"
            - 如果文章存在且内容有变化 → 更新记录，返回 "updated"
            - 如果文章存在且内容无变化 → 跳过，返回 "exists"

        参数:
            article: 文章信息字典，必须包含 url 和 title

        返回:
            "new"（新增）、"updated"（更新）、"exists"（未变化）
        """
        url = article.get("url", "")
        title = article.get("title", "")
        pub_date = article.get("pub_date", "")
        author = article.get("author", "")
        summary = article.get("summary", "")

        # 检查文章是否已存在
        existing = self.get_article(url)

        if existing is None:
            # 文章不存在，插入新记录
            self._execute(
                """
                INSERT INTO articles (url, title, pub_date, author, summary, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (url, title, pub_date, author, summary, _iso_now(), _iso_now()),
            )
            return "new"

        # 文章已存在，检查内容是否有变化
        has_changed = (
            existing.get("title") != title
            or existing.get("pub_date") != pub_date
            or existing.get("author") != author
            or existing.get("summary") != summary
        )

        if has_changed:
            # 内容有变化，更新记录
            self._execute(
                """
                UPDATE articles
                SET title = ?, pub_date = ?, author = ?, summary = ?, updated_at = ?
                WHERE url = ?
                """,
                (title, pub_date, author, summary, _iso_now(), url),
            )
            return "updated"

        # 内容无变化，跳过
        return "exists"

    def get_all_articles(self, order_by: str = "pub_date DESC") -> list[dict]:
        """
        获取所有文章

        参数:
            order_by: 排序字段和方向，默认按发布日期倒序

        返回:
            文章信息列表
        """
        # 防止 SQL 注入：只允许白名单中的排序字段
        allowed_orders = {
            "pub_date DESC", "pub_date ASC",
            "created_at DESC", "created_at ASC",
            "title ASC", "title DESC",
        }
        if order_by not in allowed_orders:
            order_by = "pub_date DESC"

        return self._execute(
            f"SELECT * FROM articles ORDER BY {order_by}",
            fetch_all=True,
        )

    def get_article_count(self) -> int:
        """
        获取文章总数

        返回:
            文章数量
        """
        result = self._execute(
            "SELECT COUNT(*) as count FROM articles",
            fetch_one=True,
        )
        return result.get("count", 0) if result else 0

    def delete_article(self, url: str) -> bool:
        """
        删除指定文章

        参数:
            url: 文章 URL

        返回:
            True 如果删除成功，否则 False
        """
        cursor = self._execute(
            "DELETE FROM articles WHERE url = ?",
            (url,),
        )
        return cursor.rowcount > 0

    # =========================================================================
    # 爬取记录
    # =========================================================================

    def begin_crawl(self, mode: str = "quick") -> int:
        """
        开始一次爬取，创建记录

        参数:
            mode: 爬取模式，"quick"（快速）或 "full"（完整）

        返回:
            crawl_record_id（爬取记录 ID）
        """
        with self._lock:
            conn = self._get_connection()
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO crawl_records (crawl_time, mode, status)
                    VALUES (?, ?, 'running')
                    """,
                    (_iso_now(), mode),
                )
                conn.commit()
                return cursor.lastrowid
            except sqlite3.Error as e:
                print(f"[数据库] 创建爬取记录失败: {e}")
                raise

    def update_crawl_stats(self, crawl_id: int, **kwargs):
        """
        更新爬取统计信息

        参数:
            crawl_id: 爬取记录 ID
            **kwargs: 要更新的统计字段，如 total_found=10, new_count=5
        """
        if not kwargs:
            return

        # 构建 SET 子句
        set_clause = ", ".join(f"{key} = ?" for key in kwargs)
        values = list(kwargs.values()) + [crawl_id]

        self._execute(
            f"UPDATE crawl_records SET {set_clause} WHERE id = ?",
            tuple(values),
        )

    def finish_crawl(self, crawl_id: int, status: str = "success",
                     error_detail: str = None, duration: float = 0):
        """
        完成一次爬取，更新最终状态和耗时

        参数:
            crawl_id: 爬取记录 ID
            status: 最终状态，"success"、"failed" 或 "partial"
            error_detail: 错误详情（仅在失败时提供）
            duration: 爬取耗时（秒）
        """
        self._execute(
            """
            UPDATE crawl_records
            SET status = ?, duration_seconds = ?, error_detail = ?
            WHERE id = ?
            """,
            (status, duration, error_detail, crawl_id),
        )

    def get_crawl_history(self, limit: int = 20) -> list[dict]:
        """
        获取爬取历史（最近的记录）

        参数:
            limit: 返回的记录数量上限

        返回:
            爬取记录列表，按时间倒序
        """
        return self._execute(
            "SELECT * FROM crawl_records ORDER BY crawl_time DESC LIMIT ?",
            (limit,),
            fetch_all=True,
        )

    def get_latest_crawl(self) -> Optional[dict]:
        """
        获取最近一次爬取记录

        返回:
            最近一次爬取的信息字典，如果没有记录则返回 None
        """
        return self._execute(
            "SELECT * FROM crawl_records ORDER BY crawl_time DESC LIMIT 1",
            fetch_one=True,
        )

    # =========================================================================
    # 失败记录
    # =========================================================================

    def add_failure(self, url: str, error: str, crawl_id: int):
        """
        记录一次爬取失败的文章

        参数:
            url: 失败的文章 URL
            error: 错误信息
            crawl_id: 关联的爬取记录 ID
        """
        self._execute(
            """
            INSERT INTO crawl_failures (url, error_message, crawl_record_id)
            VALUES (?, ?, ?)
            """,
            (url, error, crawl_id),
        )

    def get_failures(self, limit: int = 50) -> list[dict]:
        """
        获取失败记录

        参数:
            limit: 返回的记录数量上限

        返回:
            失败记录列表，按时间倒序
        """
        return self._execute(
            """
            SELECT f.*, r.mode as crawl_mode, r.status as crawl_status
            FROM crawl_failures f
            LEFT JOIN crawl_records r ON f.crawl_record_id = r.id
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (limit,),
            fetch_all=True,
        )

    # =========================================================================
    # 统计信息
    # =========================================================================

    def get_stats(self) -> dict:
        """
        获取综合统计信息

        返回:
            包含以下字段的字典:
                - total_articles: 文章总数
                - total_crawls: 爬取总次数
                - successful_crawls: 成功爬取次数
                - failed_crawls: 失败爬取次数
                - total_failures: 失败记录总数
                - last_crawl: 最近一次爬取信息（如果有）
        """
        # 文章总数
        article_count = self.get_article_count()

        # 爬取次数统计
        crawl_stats = self._execute(
            """
            SELECT
                COUNT(*) as total_crawls,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful_crawls,
                SUM(CASE WHEN status IN ('failed', 'partial') THEN 1 ELSE 0 END) as failed_crawls
            FROM crawl_records
            """,
            fetch_one=True,
        )

        # 失败记录总数
        failure_count = self._execute(
            "SELECT COUNT(*) as count FROM crawl_failures",
            fetch_one=True,
        )

        # 最近一次爬取
        latest_crawl = self.get_latest_crawl()

        return {
            "total_articles": article_count,
            "total_crawls": crawl_stats.get("total_crawls", 0) if crawl_stats else 0,
            "successful_crawls": crawl_stats.get("successful_crawls", 0) if crawl_stats else 0,
            "failed_crawls": crawl_stats.get("failed_crawls", 0) if crawl_stats else 0,
            "total_failures": failure_count.get("count", 0) if failure_count else 0,
            "last_crawl": latest_crawl,
        }

    def close(self):
        """关闭数据库连接"""
        if self._conn is not None:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass
            finally:
                self._conn = None

    def __del__(self):
        """析构函数：确保关闭连接"""
        self.close()
