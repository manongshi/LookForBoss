"""Summaries of collected job records, using comparable monthly salaries only."""
import re
import statistics
import unicodedata
from collections import Counter, defaultdict


def monthly_salary(value):
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).upper()
    if not text or "面议" in text:
        return None, "薪资未标注 / 面议"
    if re.search(r"年薪|/年|每年|/天|/日|/时|每天|每日|每小时|时薪|日薪|/次|每次|周薪|/周", text):
        return None, "年薪 / 日薪 / 时薪等其他口径"
    if any(word in text for word in ("以上", "以下", "起", "至多", "至低")):
        return None, "薪资格式或范围待确认"
    pattern = r"^(\d+(?:\.\d+)?)(万|千|K|元)?(?:[-—–~至](\d+(?:\.\d+)?)(万|千|K|元)?)?(?:元)?(?:/月|每月|月薪)?(?:[·•*×xX乘](\d{1,2})薪)?$"
    match = re.fullmatch(pattern, text)
    if not match:
        return None, "薪资格式或范围待确认"
    first_unit = match[2] or match[4]
    second_unit = match[4] or match[2]
    explicit_month = any(marker in text for marker in ("/月", "每月", "月薪"))
    if not explicit_month and first_unit not in ("K", "千") and second_unit not in ("K", "千"):
        return None, "薪资格式或范围待确认"
    factors = {"万": 10, "千": 1, "K": 1, "元": 0.001, None: 0.001}
    low = float(match[1]) * factors[first_unit]
    high = float(match[3]) * factors[second_unit] if match[3] else low
    if low <= 0 or high < low or high > 1000:
        return None, "薪资格式或范围待确认"
    return (low + high) / 2, None


def summarize_jobs(rows):
    cities = defaultdict(lambda: {"count": 0, "salaries": []})
    platforms, experience, excluded = Counter(), Counter(), Counter()
    salaries = []
    bounds = [5, 10, 15, 20, 30, 50]
    buckets = [0] * 7
    total = 0
    latest = None
    for row in rows:
        total += 1
        city = str(row.get("city") or "").strip() or "地区未标注"
        cities[city]["count"] += 1
        platforms[row.get("source") or "boss"] += 1
        experience[str(row.get("experience") or "").strip() or "经验未标注"] += 1
        timestamp = row.get("last_seen")
        if timestamp and (latest is None or timestamp > latest):
            latest = timestamp
        salary, reason = monthly_salary(row.get("salary"))
        if salary is None:
            excluded[reason] += 1
            continue
        salaries.append(salary)
        cities[city]["salaries"].append(salary)
        buckets[next((i for i, bound in enumerate(bounds) if salary < bound), 6)] += 1
    city_rows = []
    for name, item in cities.items():
        values = item["salaries"]
        city_rows.append({"name": name, "count": item["count"], "salary_count": len(values),
                          "mean": round(statistics.mean(values), 1) if values else None,
                          "median": round(statistics.median(values), 1) if values else None})
    return {
        "total": total, "city_count": len(cities), "salary_count": len(salaries),
        "mean": round(statistics.mean(salaries), 1) if salaries else None,
        "median": round(statistics.median(salaries), 1) if salaries else None,
        "latest": latest,
        "salary_buckets": [{"name": name, "count": count} for name, count in zip(
            ["5K 以下", "5–10K", "10–15K", "15–20K", "20–30K", "30–50K", "50K 及以上"], buckets)],
        "cities": sorted(city_rows, key=lambda x: (-x["count"], x["name"])),
        "platforms": [{"name": name, "count": count} for name, count in platforms.most_common()],
        "experience": [{"name": name, "count": count} for name, count in experience.most_common()],
        "excluded": [{"name": name, "count": count} for name, count in excluded.most_common()],
    }
