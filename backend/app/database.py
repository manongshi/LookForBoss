import csv
import hashlib
import io
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .config import settings


sqlite3.register_adapter(date, lambda value: value.isoformat())
sqlite3.register_adapter(datetime, lambda value: value.isoformat(" ", timespec="microseconds"))
sqlite3.register_converter("DATETIME", lambda value: datetime.fromisoformat(value.decode("utf-8")))


def now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None)


def json_dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def scalar(value):
    if hasattr(value, "read"):
        value = value.read()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, datetime):
        return value.isoformat() + "+08:00"
    return value


class DatabaseUnavailable(RuntimeError):
    pass


class Database:
    def __init__(self):
        self.ready = False
        self.message = "数据库尚未连接"
        # 单进程内串行执行写事务，避免同一岗位、同一日志序号并发入库。
        self.lock = threading.RLock()

    def table(self, name: str) -> str:
        return f'"FB_{name}"'

    @contextmanager
    def cursor(self, require_ready=True):
        if require_ready and not self.ready:
            raise DatabaseUnavailable(self.message)
        conn = None
        cur = None
        try:
            settings.database_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                settings.database_path,
                timeout=15,
                detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
                isolation_level=None,
            )
            conn.execute("PRAGMA busy_timeout=15000")
            if not require_ready:
                conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN")
            cur = conn.cursor()
            yield cur
            conn.commit()
        except DatabaseUnavailable:
            raise
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            # 不把包含本地文件路径的驱动异常原文返回给前端。
            code = getattr(exc, "sqlite_errorcode", 0) & 0xFF
            if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                message = "SQLite 数据库正在使用，请稍后重试。"
            elif code in (sqlite3.SQLITE_READONLY, sqlite3.SQLITE_CANTOPEN) or isinstance(exc, OSError):
                message = "无法读写本地 SQLite 数据库，请确认数据目录存在并且可写。"
            elif code in (sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB):
                message = "本地 SQLite 数据文件无法读取，请从备份恢复。"
            else:
                message = "SQLite 操作失败，请检查本地数据文件与表结构。"
            raise DatabaseUnavailable(message) from exc
        finally:
            if cur is not None:
                try:
                    cur.close()
                except Exception:
                    pass
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    @staticmethod
    def rows(cur):
        names = [column[0].lower() for column in cur.description]
        return [dict(zip(names, map(scalar, row))) for row in cur.fetchall()]

    def initialize(self):
        definitions = {
            "ASSISTANT": """
                ID TEXT COLLATE NOCASE NOT NULL PRIMARY KEY, PAYLOAD TEXT, UPDATED_AT DATETIME
            """,
            "TASKS": """
                ID TEXT COLLATE NOCASE NOT NULL PRIMARY KEY, NAME TEXT, STATUS TEXT,
                CONFIG_JSON TEXT, CREATED_AT DATETIME, STARTED_AT DATETIME,
                FINISHED_AT DATETIME, SCANNED INTEGER DEFAULT 0, SAVED INTEGER DEFAULT 0,
                DUPLICATES INTEGER DEFAULT 0, FAILED INTEGER DEFAULT 0,
                CURRENT_KEYWORD TEXT, CURRENT_CITY TEXT COLLATE NOCASE, MESSAGE TEXT
            """,
            "JOBS": """
                ID TEXT COLLATE NOCASE NOT NULL PRIMARY KEY, TITLE TEXT COLLATE NOCASE,
                COMPANY TEXT COLLATE NOCASE, SOURCE TEXT COLLATE NOCASE DEFAULT 'boss',
                SALARY TEXT, CITY TEXT COLLATE NOCASE, EXPERIENCE TEXT,
                DEGREE TEXT, PAYLOAD TEXT, FIRST_SEEN DATETIME, LAST_SEEN DATETIME
            """,
            "TASK_JOBS": """
                TASK_ID TEXT COLLATE NOCASE NOT NULL, JOB_ID TEXT COLLATE NOCASE NOT NULL,
                PRIMARY KEY (TASK_ID, JOB_ID)
            """,
            "JOB_KEYWORDS": """
                TASK_ID TEXT COLLATE NOCASE NOT NULL, JOB_ID TEXT COLLATE NOCASE NOT NULL,
                KEYWORD TEXT COLLATE NOCASE NOT NULL,
                PRIMARY KEY (TASK_ID, JOB_ID, KEYWORD)
            """,
            "LOGS": """
                TASK_ID TEXT COLLATE NOCASE NOT NULL, SEQ INTEGER NOT NULL, LEVEL TEXT, MESSAGE TEXT,
                CREATED_AT DATETIME, PRIMARY KEY (TASK_ID, SEQ)
            """,
            "DELIVERIES": """
                ID TEXT COLLATE NOCASE NOT NULL PRIMARY KEY, JOB_ID TEXT COLLATE NOCASE,
                TASK_ID TEXT COLLATE NOCASE, ACTION TEXT, STATUS TEXT, MESSAGE TEXT, UPDATED_AT DATETIME
            """,
            "MESSAGE_RECORDS": """
                ID TEXT COLLATE NOCASE NOT NULL PRIMARY KEY, TASK_ID TEXT COLLATE NOCASE,
                JOB_ID TEXT COLLATE NOCASE, PLATFORM TEXT, JOB_TITLE TEXT COLLATE NOCASE,
                COMPANY TEXT COLLATE NOCASE, RECRUITER TEXT COLLATE NOCASE, JOB_URL TEXT, CONTENT TEXT,
                STATUS TEXT, RESULT_MESSAGE TEXT,
                CREATED_AT DATETIME, SENT_AT DATETIME, UPDATED_AT DATETIME
            """,
        }
        indexes = {
            "IX_TASKS_CREATED": ("TASKS", "CREATED_AT"),
            "IX_JOBS_LAST_SEEN": ("JOBS", "LAST_SEEN"),
            "IX_JOBS_CITY": ("JOBS", "CITY"),
            "IX_TASK_JOBS_JOB": ("TASK_JOBS", "JOB_ID"),
            "IX_JOB_KEYWORDS_JOB": ("JOB_KEYWORDS", "JOB_ID, KEYWORD"),
            "IX_MESSAGE_TIME": ("MESSAGE_RECORDS", "CREATED_AT"),
            "IX_MESSAGE_JOB": ("MESSAGE_RECORDS", "JOB_ID"),
            "IX_MESSAGE_STATUS": ("MESSAGE_RECORDS", "STATUS, CREATED_AT"),
            "IX_MESSAGE_TASK": ("MESSAGE_RECORDS", "TASK_ID"),
        }
        with self.lock:
            self.ready = False
            try:
                with self.cursor(require_ready=False) as cur:
                    for name, columns in definitions.items():
                        cur.execute(f"CREATE TABLE IF NOT EXISTS {self.table(name)} ({columns})")
                    cur.execute(f"PRAGMA table_info({self.table('JOBS')})")
                    if not any(column[1].upper() == "SOURCE" for column in cur.fetchall()):
                        cur.execute(f"ALTER TABLE {self.table('JOBS')} ADD COLUMN SOURCE TEXT COLLATE NOCASE DEFAULT 'boss'")
                    for name, (table, columns) in indexes.items():
                        cur.execute(f'CREATE INDEX IF NOT EXISTS "{name}" ON {self.table(table)} ({columns})')
                    self._backfill_job_keywords(cur)
                    cur.execute(
                        f"UPDATE {self.table('TASKS')} SET STATUS = 'interrupted', FINISHED_AT = ?, "
                        "MESSAGE = '后端已重启，上次任务已中断，已入库岗位保留。' "
                        "WHERE STATUS IN ('running', 'waiting', 'stopping', 'queued')",
                        (now(),),
                    )
                    cur.execute(f"SELECT JOB_ID, ACTION FROM {self.table('DELIVERIES')} WHERE STATUS='pending'")
                    interrupted = cur.fetchall()
                    for job_id, action in interrupted:
                        self._delivery_status(cur, job_id, action, "unknown", "任务中断，投递结果待人工核对")
                    self._backfill_message_records(cur)
                    self._finalize_message_records(cur)
                self.ready = True
                self.message = "本地 SQLite 已连接"
            except DatabaseUnavailable as exc:
                self.message = str(exc)
        return {"connected": self.ready, "message": self.message, "name": settings.database_name}

    def _create_message_record(self, cur, task_id, job_id, content, created_at,
                               status="queued", result="等待发送", updated_at=None):
        cur.execute(f"SELECT TITLE, COMPANY, SOURCE, PAYLOAD FROM {self.table('JOBS')} WHERE ID=?", (job_id,))
        row = cur.fetchone()
        title, company, platform, payload = row if row else ("已删除职位", "", "boss", "{}")
        details = json.loads(scalar(payload) or "{}")
        updated_at = updated_at or created_at
        cur.execute(
            f"INSERT OR IGNORE INTO {self.table('MESSAGE_RECORDS')} "
            "(ID,TASK_ID,JOB_ID,PLATFORM,JOB_TITLE,COMPANY,RECRUITER,JOB_URL,CONTENT,STATUS,RESULT_MESSAGE,CREATED_AT,SENT_AT,UPDATED_AT) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id + ":" + job_id, task_id, job_id, platform, title, company,
             str(details.get("hr_name") or "")[:512], str(details.get("url") or "")[:2048], content,
             status, result[:2000], created_at, updated_at if status == "confirmed" else None, updated_at),
        )

    def _backfill_message_records(self, cur):
        cur.execute(
            f"SELECT ID,CONFIG_JSON,STATUS,CREATED_AT,FINISHED_AT,SCANNED FROM {self.table('TASKS')} "
            "WHERE CONFIG_JSON LIKE ? ORDER BY CREATED_AT",
            ('%"delivery_action"%"message"%',),
        )
        for task_id, raw_config, task_status, created_at, finished_at, scanned in cur.fetchall():
            config = json.loads(scalar(raw_config) or "{}")
            if config.get("delivery_action") != "message" or not isinstance(config.get("messages"), dict):
                continue
            cur.execute(f"SELECT JOB_ID FROM {self.table('MESSAGE_RECORDS')} WHERE TASK_ID=?", (task_id,))
            existing = {row[0] for row in cur.fetchall()}
            missing = [(job_id, content) for job_id, content in config["messages"].items()
                       if job_id not in existing and isinstance(content, str)]
            if not missing:
                continue
            cur.execute(f"SELECT JOB_ID,STATUS,MESSAGE,UPDATED_AT FROM {self.table('DELIVERIES')} WHERE TASK_ID=? AND ACTION='message'", (task_id,))
            deliveries = {job_id: (status, message, stamp) for job_id, status, message, stamp in cur.fetchall()}
            cur.execute(f"SELECT LEVEL,MESSAGE,CREATED_AT FROM {self.table('LOGS')} WHERE TASK_ID=? ORDER BY SEQ", (task_id,))
            logs = cur.fetchall()
            cur.execute(
                f"SELECT j.ID,j.TITLE FROM {self.table('JOBS')} j JOIN {self.table('TASK_JOBS')} tj ON tj.JOB_ID=j.ID WHERE tj.TASK_ID=?",
                (task_id,),
            )
            titles = dict(cur.fetchall())
            job_positions = {job_id: index for index, job_id in enumerate(config.get("job_ids", []))}
            for job_id, content in missing:
                handled = job_positions.get(job_id, 0) < (scanned or 0)
                status = "queued" if task_status in {"queued", "running", "waiting", "stopping"} else "unknown" if handled else "not_sent"
                reason = "等待发送" if status == "queued" else "历史任务缺少逐条发送结果，请核对官网记录" if handled else "任务已结束，该消息未执行发送"
                stamp = finished_at or created_at
                if job_id in deliveries:
                    status, reason, stamp = deliveries[job_id]
                    reason = reason or ""
                    if "已有相同消息" in reason:
                        status = "skipped"
                else:
                    title = titles.get(job_id)
                    # Old logs identify jobs by title. Only infer a per-job result
                    # when that title was unique within the original task.
                    matches = [(level, text, at) for level, text, at in logs
                               if title and (text.startswith(title + "：") or text.startswith("跳过 " + title + "："))]
                    if matches and list(titles.values()).count(title) == 1:
                        level, reason, stamp = matches[-1]
                        if reason.startswith("跳过 ") or "已有相同消息" in reason:
                            status = "skipped"
                        elif level == "success" and "确认新消息发送完成" in reason:
                            status = "confirmed"
                        elif "待核对" in reason:
                            status = "unknown"
                        else:
                            status = "failed"
                    elif matches:
                        status, reason = "unknown", "历史任务包含同名职位，请核对官网确认发送结果"
                self._create_message_record(cur, task_id, job_id, content, created_at, status, reason, stamp)

    def _message_record_status(self, cur, task_id, job_id, status, message, timestamp=None):
        timestamp = timestamp or now()
        cur.execute(
            f"UPDATE {self.table('MESSAGE_RECORDS')} SET STATUS=?,RESULT_MESSAGE=?,UPDATED_AT=?,"
            "SENT_AT=CASE WHEN ?='confirmed' THEN COALESCE(SENT_AT,?) ELSE SENT_AT END WHERE TASK_ID=? AND JOB_ID=?",
            (status, message[:2000], timestamp, status, timestamp, task_id, job_id),
        )

    def message_record_status(self, task_id, job_id, status, message):
        with self.lock, self.cursor() as cur:
            self._message_record_status(cur, task_id, job_id, status, message)

    def _finalize_message_records(self, cur, task_id=None):
        scope = " AND TASK_ID=?" if task_id else ""
        params = (task_id,) if task_id else ()
        cur.execute(
            f"UPDATE {self.table('MESSAGE_RECORDS')} SET STATUS='not_sent',RESULT_MESSAGE='任务已结束，该消息未执行发送',UPDATED_AT=? "
            f"WHERE STATUS='queued'{scope}", (now(), *params),
        )
        cur.execute(
            f"UPDATE {self.table('MESSAGE_RECORDS')} SET STATUS='unknown',RESULT_MESSAGE='任务中断，请核对官网消息记录',UPDATED_AT=? "
            f"WHERE STATUS='pending'{scope}", (now(), *params),
        )

    def list_message_records(self, q="", status="", platform="", job_id="", task_id="",
                             date_from=None, date_to=None, page=1, page_size=20):
        clauses, params = [], []
        if q:
            clauses.append("(m.JOB_TITLE LIKE ? OR m.COMPANY LIKE ? OR m.RECRUITER LIKE ? OR m.CONTENT LIKE ?)")
            params.extend(["%" + q + "%"] * 4)
        for column, value in (("STATUS", status), ("PLATFORM", platform), ("JOB_ID", job_id), ("TASK_ID", task_id)):
            if value:
                clauses.append(f"m.{column}=?")
                params.append(value)
        if date_from:
            clauses.append("COALESCE(m.SENT_AT,m.CREATED_AT)>=?")
            params.append(date_from)
        if date_to:
            clauses.append("COALESCE(m.SENT_AT,m.CREATED_AT)<?")
            params.append(date_to + timedelta(days=1))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self.table('MESSAGE_RECORDS')} m{where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"SELECT m.*,t.NAME AS TASK_NAME FROM {self.table('MESSAGE_RECORDS')} m "
                f"LEFT JOIN {self.table('TASKS')} t ON t.ID=m.TASK_ID{where} "
                "ORDER BY COALESCE(m.SENT_AT,m.CREATED_AT) DESC,m.ID DESC LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            )
            items = self.rows(cur)
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def _backfill_job_keywords(self, cur):
        # 历史数据只恢复已记录的实际搜索词，不把任务的所有关键词分配给每个岗位。
        cur.execute(
            f"SELECT j.ID, j.PAYLOAD, tj.TASK_ID, t.CONFIG_JSON FROM {self.table('JOBS')} j "
            f"LEFT JOIN {self.table('TASK_JOBS')} tj ON tj.JOB_ID=j.ID "
            f"LEFT JOIN {self.table('TASKS')} t ON t.ID=tj.TASK_ID "
            f"WHERE NOT EXISTS (SELECT 1 FROM {self.table('JOB_KEYWORDS')} k WHERE k.JOB_ID=j.ID)"
        )
        rows = cur.fetchall()
        for job_id, payload, task_id, config_json in rows:
            keyword = str(json.loads(scalar(payload)).get("keyword") or "").strip()
            if not keyword:
                continue
            config = json.loads(scalar(config_json)) if config_json else {}
            if config.get("mode") == "delivery":
                continue
            if task_id and keyword not in config.get("keywords", []):
                continue
            self._record_job_keyword(cur, task_id or "", job_id, keyword)

    def _record_job_keyword(self, cur, task_id, job_id, keyword):
        keyword = str(keyword or "").strip()
        if not keyword:
            return
        cur.execute(
            f"SELECT COUNT(*) FROM {self.table('JOB_KEYWORDS')} WHERE TASK_ID=? AND JOB_ID=? AND KEYWORD=?",
            (task_id, job_id, keyword),
        )
        if not cur.fetchone()[0]:
            cur.execute(
                f"INSERT INTO {self.table('JOB_KEYWORDS')} (TASK_ID,JOB_ID,KEYWORD) VALUES (?,?,?)",
                (task_id, job_id, keyword),
            )

    def record_job_keyword(self, task_id, job):
        job_id = hashlib.sha256(f"{job.get('source', 'boss')}:{job['platform_id']}".encode()).hexdigest()[:32]
        with self.lock, self.cursor() as cur:
            self._record_job_keyword(cur, task_id, job_id, job.get("keyword"))

    def get_assistant(self, key, default=None):
        with self.cursor() as cur:
            cur.execute(f"SELECT PAYLOAD FROM {self.table('ASSISTANT')} WHERE ID=?", (key,))
            row = cur.fetchone()
        return json.loads(scalar(row[0])) if row else default

    def save_assistant(self, key, payload):
        with self.lock, self.cursor() as cur:
            cur.execute(f"INSERT INTO {self.table('ASSISTANT')} (ID,PAYLOAD,UPDATED_AT) VALUES (?,?,?) "
                        "ON CONFLICT(ID) DO UPDATE SET PAYLOAD=excluded.PAYLOAD,UPDATED_AT=excluded.UPDATED_AT",
                        (key, json_dump(payload), now()))
        return payload

    def delete_assistant(self, key):
        with self.lock, self.cursor() as cur:
            cur.execute(f"DELETE FROM {self.table('ASSISTANT')} WHERE ID=?", (key,))

    def blacklist(self):
        with self.cursor() as cur:
            cur.execute(f"SELECT PAYLOAD FROM {self.table('ASSISTANT')} WHERE ID LIKE ? ORDER BY UPDATED_AT DESC", ("blacklist:%",))
            return [json.loads(scalar(row[0])) for row in cur.fetchall()]

    def job_blacklist_hits(self, job):
        from .job_assistant import blacklist_hits
        return blacklist_hits(job, self.blacklist())

    def create_task(self, config: dict) -> dict:
        task_id = str(uuid.uuid4())
        created_at = now()
        name = config.get("name", "").strip() or (
            " / ".join(config["keywords"]) + " · " + "、".join(city["name"] for city in config["cities"])
        )
        with self.lock, self.cursor() as cur:
            cur.execute(
                f"INSERT INTO {self.table('TASKS')} "
                "(ID, NAME, STATUS, CONFIG_JSON, CREATED_AT, MESSAGE) VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, name[:120], "queued", json_dump(config), created_at, "等待采集"),
            )
            for job_id in config.get("job_ids", []):
                cur.execute(f"INSERT INTO {self.table('TASK_JOBS')} (TASK_ID, JOB_ID) VALUES (?,?)", (task_id, job_id))
                if config.get("delivery_action") == "message":
                    self._create_message_record(cur, task_id, job_id, config.get("messages", {}).get(job_id, ""), created_at)
        return self.get_task(task_id)

    def get_task(self, task_id: str):
        with self.cursor() as cur:
            cur.execute(f"SELECT * FROM {self.table('TASKS')} WHERE ID = ?", (task_id,))
            rows = self.rows(cur)
        if not rows:
            return None
        result = rows[0]
        result["config"] = json.loads(result.pop("config_json"))
        return result

    def list_tasks(self):
        with self.cursor() as cur:
            cur.execute(f"SELECT * FROM {self.table('TASKS')} ORDER BY CREATED_AT DESC LIMIT 100")
            rows = self.rows(cur)
        for row in rows:
            row["config"] = json.loads(row.pop("config_json"))
        return rows

    def update_task(self, task_id: str, **values):
        allowed = {
            "status", "started_at", "finished_at", "scanned", "saved", "duplicates",
            "failed", "current_keyword", "current_city", "message",
        }
        values = {key: value for key, value in values.items() if key in allowed}
        if not values:
            return
        with self.lock, self.cursor() as cur:
            assignment = ", ".join(f"{key.upper()} = ?" for key in values)
            cur.execute(
                f"UPDATE {self.table('TASKS')} SET {assignment} WHERE ID = ?",
                (*values.values(), task_id),
            )

    def request_stop(self, task_id: str):
        with self.lock, self.cursor() as cur:
            cur.execute(
                f"UPDATE {self.table('TASKS')} SET STATUS='stopping', "
                "MESSAGE='正在停止，已采集岗位会保留' WHERE ID=? "
                "AND STATUS IN ('queued', 'running', 'waiting', 'stopping')",
                (task_id,),
            )

    def interrupt_task(self, task_id: str, message: str):
        with self.lock, self.cursor() as cur:
            cur.execute(
                f"UPDATE {self.table('TASKS')} SET STATUS='interrupted', FINISHED_AT=?, "
                "MESSAGE=? WHERE ID=? "
                "AND STATUS IN ('queued', 'running', 'waiting', 'stopping')",
                (now(), message[:500], task_id),
            )

    def log(self, task_id: str, message: str, level="info"):
        with self.lock, self.cursor() as cur:
            cur.execute(f"SELECT COALESCE(MAX(SEQ), 0) FROM {self.table('LOGS')} WHERE TASK_ID = ?", (task_id,))
            sequence = int(cur.fetchone()[0]) + 1
            cur.execute(
                f"INSERT INTO {self.table('LOGS')} (TASK_ID, SEQ, LEVEL, MESSAGE, CREATED_AT) "
                "VALUES (?, ?, ?, ?, ?)",
                (task_id, sequence, level, message[:500], now()),
            )

    def get_logs(self, task_id: str, after=0):
        with self.cursor() as cur:
            cur.execute(
                f"SELECT SEQ, LEVEL, MESSAGE, CREATED_AT FROM {self.table('LOGS')} "
                "WHERE TASK_ID = ? AND SEQ > ? ORDER BY SEQ LIMIT 200",
                (task_id, after),
            )
            return self.rows(cur)

    def save_job(self, task_id: str, job: dict):
        job_id = hashlib.sha256(f"{job.get('source', 'boss')}:{job['platform_id']}".encode()).hexdigest()[:32]
        job["id"] = job_id
        timestamp = now()
        with self.lock, self.cursor() as cur:
            cur.execute(f"SELECT FIRST_SEEN, PAYLOAD FROM {self.table('JOBS')} WHERE ID = ?", (job_id,))
            existing = cur.fetchone()
            if existing:
                previous = json.loads(scalar(existing[1]))
                for key in ("delivery_status", "delivery_action", "delivery_message", "delivery_updated_at"):
                    if key in previous:
                        job[key] = previous[key]
                # 列表先入库、详情后补充；刷新列表不能清空已有的完整详情。
                for key in ("description", "description_source", "address", "company_description", "hr_name", "hr_title", "hr_active", "industry", "scale", "stage", "tags"):
                    if not job.get(key) and previous.get(key):
                        job[key] = previous[key]
                if not job.get("salary") and previous.get("salary"):
                    for key in ("salary", "salary_source", "salary_min", "salary_max", "salary_unit", "salary_months"):
                        job[key] = previous.get(key)
                if job.get("description"):
                    job["detail_status"] = "complete"
            fields = (job["title"], job["company"], job["salary"], job["city"], job["experience"], job["degree"], json_dump(job))
            if existing:
                cur.execute(
                    f"UPDATE {self.table('JOBS')} SET TITLE=?, COMPANY=?, SALARY=?, CITY=?, "
                    "EXPERIENCE=?, DEGREE=?, PAYLOAD=?, LAST_SEEN=? WHERE ID=?",
                    (*fields, timestamp, job_id),
                )
            else:
                cur.execute(
                    f"INSERT INTO {self.table('JOBS')} "
                    "(TITLE, COMPANY, SALARY, CITY, EXPERIENCE, DEGREE, PAYLOAD, LAST_SEEN, FIRST_SEEN, ID) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (*fields, timestamp, timestamp, job_id),
                )
            cur.execute(f"UPDATE {self.table('JOBS')} SET SOURCE=? WHERE ID=?", (job.get("source", "boss"), job_id))
            cur.execute(f"SELECT COUNT(*) FROM {self.table('TASK_JOBS')} WHERE TASK_ID=? AND JOB_ID=?", (task_id, job_id))
            if not cur.fetchone()[0]:
                cur.execute(f"INSERT INTO {self.table('TASK_JOBS')} (TASK_ID, JOB_ID) VALUES (?, ?)", (task_id, job_id))
            self._record_job_keyword(cur, task_id, job_id, job.get("keyword"))
        return not bool(existing)

    def _where(self, q="", city="", task_id="", platform="", keyword=""):
        conditions = []
        params = []
        if platform:
            conditions.append("j.SOURCE = ?")
            params.append(platform)
        if q:
            conditions.append("(LOWER(j.TITLE) LIKE ? OR LOWER(j.COMPANY) LIKE ?)")
            params.extend([f"%{q.lower()}%"] * 2)
        if city:
            conditions.append("j.CITY = ?")
            params.append(city)
        if task_id:
            conditions.append(f"EXISTS (SELECT 1 FROM {self.table('TASK_JOBS')} tj WHERE tj.JOB_ID=j.ID AND tj.TASK_ID=?)")
            params.append(task_id)
        if keyword:
            keyword_condition = "k.JOB_ID=j.ID AND k.KEYWORD=?"
            params.append(keyword)
            if task_id:
                keyword_condition += " AND k.TASK_ID=?"
                params.append(task_id)
            conditions.append(f"EXISTS (SELECT 1 FROM {self.table('JOB_KEYWORDS')} k WHERE {keyword_condition})")
        return (" WHERE " + " AND ".join(conditions) if conditions else ""), params

    def job_keywords(self, q="", city="", task_id="", platform=""):
        groups = {}
        with self.cursor() as cur:
            task_where = " WHERE ID=?" if task_id else ""
            cur.execute(f"SELECT CONFIG_JSON FROM {self.table('TASKS')}{task_where}", (task_id,) if task_id else ())
            for row in cur.fetchall():
                config = json.loads(scalar(row[0]))
                if config.get("mode") == "delivery" or (platform and config.get("platform", "boss") != platform):
                    continue
                if city and city not in [item["name"] for item in config.get("cities", [])]:
                    continue
                for keyword in config.get("keywords", []):
                    groups.setdefault(keyword, {"keyword": keyword, "total": 0, "last_seen": None})
            where, params = self._where(q, city, task_id, platform)
            if task_id:
                where += (" AND " if where else " WHERE ") + "k.TASK_ID=?"
                params.append(task_id)
            cur.execute(
                f'SELECT k.KEYWORD, COUNT(DISTINCT j.ID) AS TOTAL, MAX(j.LAST_SEEN) AS "LAST_SEEN [DATETIME]" '
                f"FROM {self.table('JOB_KEYWORDS')} k JOIN {self.table('JOBS')} j ON j.ID=k.JOB_ID"
                f"{where} GROUP BY k.KEYWORD ORDER BY MAX(j.LAST_SEEN) DESC, k.KEYWORD",
                params,
            )
            for row in self.rows(cur):
                groups[row["keyword"]] = row
        return sorted(groups.values(), key=lambda item: (item["last_seen"] or "", item["keyword"]), reverse=True)

    @staticmethod
    def job_record(row):
        payload = json.loads(row.pop("payload"))
        payload.update(row)
        return payload

    def list_jobs(self, q="", city="", task_id="", page=1, page_size=20, platform="", keyword=""):
        where, params = self._where(q, city, task_id, platform, keyword)
        with self.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {self.table('JOBS')} j{where}", params)
            total = int(cur.fetchone()[0])
            cur.execute(
                f"SELECT j.* FROM {self.table('JOBS')} j{where} "
                "ORDER BY j.LAST_SEEN DESC, j.ID LIMIT ? OFFSET ?",
                (*params, page_size, (page - 1) * page_size),
            )
            items = [self.job_record(row) for row in self.rows(cur)]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    def get_job(self, job_id: str):
        with self.cursor() as cur:
            cur.execute(f"SELECT * FROM {self.table('JOBS')} WHERE ID = ?", (job_id,))
            rows = self.rows(cur)
            return self.job_record(rows[0]) if rows else None

    def reserve_delivery(self, task_id, job_id, action, allow_repeat=False):
        with self.lock, self.cursor() as cur:
            delivery_id = job_id + ":" + action
            cur.execute(f"SELECT COUNT(*) FROM {self.table('DELIVERIES')} WHERE JOB_ID=? AND STATUS IN ('pending','unknown')", (job_id,))
            if cur.fetchone()[0]:
                return False
            cur.execute(f"SELECT STATUS FROM {self.table('DELIVERIES')} WHERE ID=?", (delivery_id,))
            previous = cur.fetchone()
            if previous and previous[0] not in ("not_sent", "failed") and not (
                action == "message" and allow_repeat and previous[0] == "confirmed"
            ):
                return False
            if previous:
                cur.execute(f"UPDATE {self.table('DELIVERIES')} SET TASK_ID=? WHERE ID=?", (task_id, delivery_id))
            else:
                cur.execute(f"INSERT INTO {self.table('DELIVERIES')} (ID, JOB_ID, TASK_ID, ACTION) VALUES (?,?,?,?)",
                            (delivery_id, job_id, task_id, action))
            self._delivery_status(cur, job_id, action, "pending", "准备执行，结果待网站确认")
            cur.execute(f"SELECT COUNT(*) FROM {self.table('TASK_JOBS')} WHERE TASK_ID=? AND JOB_ID=?", (task_id, job_id))
            if not cur.fetchone()[0]:
                cur.execute(f"INSERT INTO {self.table('TASK_JOBS')} (TASK_ID, JOB_ID) VALUES (?,?)", (task_id, job_id))
            return True

    def _delivery_status(self, cur, job_id, action, status, message, record_status=None):
        timestamp = now()
        cur.execute(f"UPDATE {self.table('DELIVERIES')} SET STATUS=?, MESSAGE=?, UPDATED_AT=? WHERE ID=?",
                    (status, message[:500], timestamp, job_id + ":" + action))
        if action == "message":
            cur.execute(f"SELECT TASK_ID FROM {self.table('DELIVERIES')} WHERE ID=?", (job_id + ":" + action,))
            delivery = cur.fetchone()
            if delivery:
                self._message_record_status(cur, delivery[0], job_id, record_status or status, message, timestamp)
        cur.execute(f"SELECT PAYLOAD FROM {self.table('JOBS')} WHERE ID=?", (job_id,))
        row = cur.fetchone()
        if row:
            payload = json.loads(scalar(row[0]))
            payload.update(delivery_status=status, delivery_action=action, delivery_message=message[:500],
                           delivery_updated_at=timestamp.isoformat() + "+08:00")
            cur.execute(f"UPDATE {self.table('JOBS')} SET PAYLOAD=? WHERE ID=?", (json_dump(payload), job_id))

    def delivery_status(self, job_id, action, status, message, record_status=None):
        with self.lock, self.cursor() as cur:
            self._delivery_status(cur, job_id, action, status, message, record_status)

    def record_delivery_observation(self, task_id, job_id, action, status, message):
        if status not in {"confirmed", "failed"}:
            raise ValueError("页面核对结果只能为已确认或未发送")
        with self.lock, self.cursor() as cur:
            cur.execute(f"SELECT ACTION, STATUS FROM {self.table('DELIVERIES')} WHERE JOB_ID=?", (job_id,))
            previous = cur.fetchall()
            if any(value == "pending" for _, value in previous):
                return False
            if status == "failed" and any(
                value == "unknown" or (previous_action == action and value == "confirmed")
                for previous_action, value in previous
            ):
                return False
            # Read-only website evidence may confirm an earlier uncertain attempt.
            # A failed preflight must never erase an uncertain or successful result.
            cur.execute(
                f"INSERT INTO {self.table('DELIVERIES')} (ID, JOB_ID, TASK_ID, ACTION) VALUES (?,?,?,?) "
                "ON CONFLICT(ID) DO UPDATE SET TASK_ID=excluded.TASK_ID",
                (job_id + ":" + action, job_id, task_id, action),
            )
            self._delivery_status(cur, job_id, action, status, message)
            return True

    def resolve_delivery(self, job_id, action, status):
        with self.lock, self.cursor() as cur:
            cur.execute(f"SELECT STATUS,TASK_ID FROM {self.table('DELIVERIES')} WHERE ID=?", (job_id + ":" + action,))
            previous = cur.fetchone()
            if not previous or previous[0] != "unknown":
                return False
            self._delivery_status(cur, job_id, action, status, "用户核对官网后确认" + ("已完成" if status == "confirmed" else "未发送"))
            if action == "message":
                self._sync_message_task(cur, previous[1])
            return True

    def _sync_message_task(self, cur, task_id):
        cur.execute(f"SELECT STATUS,SCANNED FROM {self.table('TASKS')} WHERE ID=?", (task_id,))
        task = cur.fetchone()
        if not task or task[0] in {"queued", "running", "waiting", "stopping"}:
            return
        cur.execute(f"SELECT STATUS,COUNT(*) FROM {self.table('MESSAGE_RECORDS')} WHERE TASK_ID=? GROUP BY STATUS", (task_id,))
        counts = dict(cur.fetchall())
        if not counts:
            return
        saved, skipped = counts.get("confirmed", 0), counts.get("skipped", 0)
        unknown = sum(counts.get(value, 0) for value in ("unknown", "pending", "queued"))
        failures, not_sent = counts.get("failed", 0), counts.get("not_sent", 0)
        # Queued recipients left behind when a task stopped are not failed
        # sends. A manually resolved attempt still counts as processed.
        resolved_not_sent = min(not_sent, max(0, (task[1] or 0) - saved - skipped - unknown - failures))
        values = {"saved": saved, "duplicates": skipped, "failed": failures + resolved_not_sent}
        if task[0] in {"unknown", "failed", "partial", "completed"}:
            if unknown:
                values.update(status="unknown", message=f"消息核对进度：新发送 {saved}，跳过 {skipped}，待核对 {unknown}，失败 {failures}")
            else:
                incomplete = failures + not_sent
                status = ("partial" if saved or skipped else "failed") if incomplete else "completed"
                values.update(status=status, message=f"消息核对完成：新发送 {saved}，跳过 {skipped}，未发送 {not_sent}，失败 {failures}")
        assignments = ", ".join(f"{key.upper()}=?" for key in values)
        cur.execute(f"UPDATE {self.table('TASKS')} SET {assignments} WHERE ID=?", (*values.values(), task_id))

    def finalize_deliveries(self, task_id):
        with self.lock, self.cursor() as cur:
            cur.execute(f"SELECT JOB_ID, ACTION FROM {self.table('DELIVERIES')} WHERE TASK_ID=? AND STATUS='pending'", (task_id,))
            for job_id, action in cur.fetchall():
                self._delivery_status(cur, job_id, action, "unknown", "任务已中断，请核对官网结果后确认状态")
            self._finalize_message_records(cur, task_id)

    def stats(self):
        with self.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) TOTAL, COUNT(DISTINCT COMPANY) COMPANIES, COUNT(DISTINCT CITY) CITIES "
                f"FROM {self.table('JOBS')}"
            )
            result = self.rows(cur)[0]
            cur.execute(f"SELECT COUNT(*) FROM {self.table('JOBS')} WHERE FIRST_SEEN >= ?", (now().replace(hour=0, minute=0, second=0, microsecond=0),))
            result["today"] = int(cur.fetchone()[0])
            cur.execute(f"SELECT COUNT(*) FROM {self.table('TASKS')}")
            result["tasks"] = int(cur.fetchone()[0])
            cur.execute(f"SELECT DISTINCT CITY FROM {self.table('JOBS')} WHERE CITY IS NOT NULL ORDER BY CITY")
            result["city_options"] = [scalar(row[0]) for row in cur.fetchall()]
        return result

    def job_distribution(self, q="", city="", platform=""):
        from .analytics import summarize_jobs
        where, params = self._where(q, city, "", platform)
        with self.cursor() as cur:
            cur.execute(f"SELECT j.SALARY,j.CITY,j.SOURCE,j.EXPERIENCE,j.LAST_SEEN FROM {self.table('JOBS')} j{where}", params)
            names = [column[0].lower() for column in cur.description]

            def records():
                while batch := cur.fetchmany(500):
                    for row in batch:
                        yield dict(zip(names, map(scalar, row)))

            result = summarize_jobs(records())
            cur.execute(f"SELECT DISTINCT CITY FROM {self.table('JOBS')} WHERE CITY IS NOT NULL AND CITY <> '' ORDER BY CITY")
            result["city_options"] = [scalar(row[0]) for row in cur.fetchall()]
        return result

    def export_csv(self, q="", city="", task_id="", platform="", keyword=""):
        where, params = self._where(q, city, task_id, platform, keyword)
        columns = {
            "source": "平台", "delivery_action": "投递方式", "delivery_status": "投递状态",
            "title": "岗位名称", "company": "公司", "salary": "薪资", "city": "城市",
            "location": "工作地点", "experience": "经验", "degree": "学历",
            "industry": "行业", "scale": "公司规模", "stage": "融资阶段",
            "hr_active": "招聘者活跃状态", "description": "职位描述", "url": "岗位链接",
            "first_seen": "首次采集", "last_seen": "最近采集",
        }
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        yield "\ufeff"
        writer.writerow(columns.values())
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)
        with self.cursor() as cur:
            cur.execute(f"SELECT j.* FROM {self.table('JOBS')} j{where} ORDER BY j.LAST_SEEN DESC, j.ID", params)
            names = [column[0].lower() for column in cur.description]
            while rows := cur.fetchmany(200):
                for row in rows:
                    record = self.job_record(dict(zip(names, map(scalar, row))))
                    values = []
                    for key in columns:
                        value = str(record.get(key) or "")
                        if value.startswith(("=", "+", "-", "@", "\t", "\r")):
                            value = "'" + value
                        values.append(value)
                    writer.writerow(values)
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)


database = Database()
