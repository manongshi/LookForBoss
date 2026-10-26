"""Evidence-based comparison and a local greeting fallback."""
import re
import unicodedata


def normalize(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).casefold()


def contains(text, term):
    text = unicodedata.normalize("NFKC", str(text or "")).casefold()
    term = unicodedata.normalize("NFKC", str(term or "")).casefold().strip()
    if not term:
        return False
    if re.fullmatch(r"[a-z0-9.+# /-]+", term):
        return bool(re.search(r"(?<![a-z0-9+#])" + re.escape(term) + r"(?![a-z0-9+#])", text))
    return normalize(term) in normalize(text)


def blacklist_hits(job, rules):
    hits = []
    for rule in rules:
        if not rule.get("enabled") or rule.get("platform") not in ("", job.get("source", "boss")):
            continue
        kind, value = rule["kind"], rule["value"]
        matched = (
            kind == "company" and normalize(value) == normalize(job.get("company"))
            or kind == "title" and contains(job.get("title"), value)
            or kind == "recruiter" and normalize(value) == normalize(job.get("hr_name"))
            and normalize(rule.get("company")) == normalize(job.get("company"))
        )
        if matched:
            hits.append(rule)
    return hits


SKILLS = ["Java", "Python", "JavaScript", "TypeScript", "C++", "C#", "Golang", "Go", "Rust",
          "Vue", "React", "Angular", "Spring", "Spring Boot", "MySQL", "Redis", "PostgreSQL",
          "MongoDB", "Docker", "Kubernetes", "Linux", "Git", "SQL", "HTML", "CSS", "Node.js",
          "Flask", "FastAPI", "Django", "Spark", "Hadoop", "Figma", "Axure", "Excel", "数据分析",
          "项目管理", "产品设计", "用户研究", "小程序", "机器学习", "深度学习"]
DEGREES = {"高中": 1, "中专": 1, "大专": 2, "本科": 3, "硕士": 4, "博士": 5}


def analyze_job(job, profile):
    items = []

    def add(label, status, evidence, explanation, weight, fraction=None):
        items.append(dict(label=label, status=status, evidence=evidence, explanation=explanation,
                          weight=weight, fraction=fraction if fraction is not None else (1 if status == "match" else 0)))

    description = str(job.get("description") or "")
    text = "\n".join([str(job.get("title") or ""), description, "、".join(job.get("tags") or [])])
    skills = profile.get("skills", [])
    vocabulary = list({normalize(s): s for s in [*SKILLS, *skills]}.values())
    mentioned = [s for s in vocabulary if contains(text, s)]
    declared = {normalize(s) for s in skills}
    matched = [s for s in mentioned if normalize(s) in declared]
    missing = [s for s in mentioned if normalize(s) not in declared]
    sentences = re.split(r"[\n。；]", description)
    evidence = "；".join(s.strip()[:160] for s in sentences if any(contains(s, x) for x in mentioned))[:600]
    if not skills or not description or not mentioned:
        add("技能关键词", "unknown", evidence or "职位描述或可识别技能信息不足", "请填写技能并补全岗位详情后再判断。", 40)
    else:
        add("技能关键词", "match" if not missing else "partial" if matched else "gap", evidence or text[:300],
            f"共同提及：{'、'.join(matched) or '暂无'}。个人资料未列出：{'、'.join(missing) or '无'}。未列出不代表不会；提及也不代表必需。",
            40, len(matched) / len(mentioned))
    roles = profile.get("roles", [])
    title = job.get("title") or ""
    add("目标岗位", "unknown" if not roles or not title else "match" if any(contains(title, r) for r in roles) else "gap",
        title or "岗位名称未标注", "你的目标：" + ("、".join(roles) or "未填写") + "；按名称关键词比较。", 15)
    cities = profile.get("cities", [])
    city = job.get("city") or ""
    add("工作城市", "unknown" if not cities or not city else "match" if any(normalize(c).removesuffix("市") == normalize(city).removesuffix("市") for c in cities) else "gap",
        city or "城市未标注", "你的意向城市：" + ("、".join(cities) or "未填写"), 15)
    experience = str(job.get("experience") or "")
    years = profile.get("years")
    minimum = re.search(r"(\d+(?:\.\d+)?)\s*(?:[-~至—–]\s*\d+(?:\.\d+)?)?\s*年", experience)
    exp_status = "unknown"
    if years is not None:
        if "不限" in experience:
            exp_status = "match"
        elif minimum and not any(s in experience for s in ("应届", "在校", "以内", "以下")):
            exp_status = "match" if years >= float(minimum[1]) else "gap"
    add("经验年限", exp_status, experience or "经验未标注", f"你填写：{years if years is not None else '未填写'} 年；仅比较明确的最低年限，应届等要求需人工确认。", 10)
    degree = str(job.get("degree") or "")
    own_degree = profile.get("degree", "")
    requirement = next((d for d in DEGREES if d in degree), None)
    degree_status = "unknown"
    if own_degree:
        if "不限" in degree:
            degree_status = "match"
        elif requirement:
            degree_status = "match" if DEGREES[own_degree] >= DEGREES[requirement] else "gap"
    add("学历", degree_status, degree or "学历未标注", "你填写：" + (own_degree or "未填写") + "；专业、全日制等附加条件需人工确认。", 10)
    salary = str(job.get("salary") or "")
    salary_min = profile.get("salary_min")
    salary_text = unicodedata.normalize("NFKC", salary).lower()
    # Only compare explicit monthly ranges; yearly/daily pay and negotiable offers remain unknown.
    pay = re.search(r"(\d+(?:\.\d+)?)\s*[-~至—–]\s*(\d+(?:\.\d+)?)\s*(k|千|万)", salary_text)
    salary_status = "unknown"
    if pay and salary_min is not None and not any(x in salary_text for x in ("/年", "年薪", "每年", "/天", "/日", "/时", "每天", "每小时", "元/次")):
        low, high = float(pay[1]), float(pay[2])
        if pay[3] == "万":
            low, high = low * 10, high * 10
        if low <= high:
            salary_status = "match" if low >= salary_min else "partial" if high >= salary_min else "gap"
    add("期望月薪", salary_status, salary or "薪资未标注", f"你的税前月薪底线：{salary_min if salary_min is not None else '未填写'} K；区间交集只代表可能符合，不保证实际薪资。", 10, 0.5 if salary_status == "partial" else None)
    known = [i for i in items if i["status"] != "unknown"]
    weight = sum(i["weight"] for i in known)
    score = round(sum(i["weight"] * i["fraction"] for i in known) / weight * 100) if weight else None
    return dict(score=score, coverage=weight, items=items, matched_skills=matched, missing_skills=missing,
                notice="规则匹配参考分，不是录用概率。仅按已填写资料和岗位原文比较；技能同义词、否定语境及隐含要求可能无法识别。未知项不计分，请结合信息覆盖度阅读。")


def greeting(job, profile, analysis):
    title = job.get("title") or "这个岗位"
    opening = f"您好，我对贵公司的「{title}」岗位很感兴趣。"
    intro = profile.get("introduction", "").strip()
    shared = analysis["matched_skills"]
    skills = f"我具备{'、'.join(shared[:5])}相关技能。" if shared else ""
    return (opening + (intro + " " if intro else "") + skills + "希望进一步了解岗位要求和团队情况，期待与您沟通。")[:1000]
