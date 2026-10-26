import json
import re
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlencode, urlparse


PlatformId = Literal["boss", "liepin", "job51", "zhilian"]
# Platform codes are reference data from get_jobs v2.0.1's empty dictionary database.
# https://github.com/loks666/get_jobs/releases/tag/v2.0.1
OPTIONS = json.loads(Path(__file__).with_name("platform_options.json").read_text())
PLATFORMS = {
    "boss": {"name": "BOSS 直聘", "domain": "zhipin.com", "login_url": "https://www.zhipin.com/web/user/",
             "entry_url": "https://www.zhipin.com/web/geek/jobs", "login_paths": ("/web/user", "/web/passport/login", "/user/login"),
             "account": ".nav-figure img, .nav-figure .label-name, .nav-user img",
             "login": ".sign-wrap, .sign-wrap-new, .sign-form, .btn-sign", "experimental": False},
    "liepin": {"name": "猎聘", "domain": "liepin.com", "login_url": "https://www.liepin.com/login",
               "entry_url": "https://www.liepin.com/zhaopin/", "login_paths": ("/login",),
               "account": "#header-quick-menu-user-info, .header-quick-menu-user-photo",
               "login": "#header-quick-menu-login, .login-dialog", "experimental": False},
    "job51": {"name": "前程无忧", "domain": "51job.com", "login_url": "https://we.51job.com/pc/search",
              "entry_url": "https://we.51job.com/pc/search", "login_paths": ("/passport", "/login"),
              "account": "a.uname, a[href*='/pc/my/myjob'], .login-info .username, .user-info",
              "login": "span.login.loginBtnClick, .login-dialog", "experimental": True},
    "zhilian": {"name": "智联招聘", "domain": "zhaopin.com", "login_url": "https://passport.zhaopin.com/login",
                "entry_url": "https://www.zhaopin.com/sou/", "login_paths": ("/login",),
                "account": ".home-header__user, .home-header__c-user, .user-info, .user-name, .username-text",
                "login": "a.home-header__c-no-login, .login-dialog", "experimental": True},
}


def belongs_to(platform, url):
    parsed = urlparse(url)
    host = parsed.hostname or ""
    domain = PLATFORMS[platform]["domain"]
    return parsed.scheme == "https" and (host == domain or host.endswith("." + domain))


def is_login_url(platform, url):
    parsed = urlparse(url)
    return any(parsed.path.startswith(path) for path in PLATFORMS[platform]["login_paths"])


def job_identity(platform, url):
    if not belongs_to(platform, url):
        return ""
    parsed = urlparse(url)
    patterns = {"boss": r"/job_detail/([^/]+)\.html", "liepin": r"/(?:job|a)/([\w-]+)\.shtml",
                "job51": r"/(\d+)\.html", "zhilian": r"/(?:jobdetail/)?([A-Za-z0-9]+)\.htm[l]?"}
    if platform == "job51":
        value = parse_qs(parsed.query).get("jobId", [""])[0]
        if value.isdigit():
            return value
    match = re.search(patterns[platform], parsed.path)
    return match[1] if match else ""


def search_url(config, keyword, city, page=1):
    if config.platform == "boss":
        params = {"query": keyword, "city": city.code, "page": page}
        params.update({key: getattr(config, key) for key in ("salary", "experience", "degree", "scale") if getattr(config, key)})
    elif config.platform == "liepin":
        params = {"key": keyword, "city": city.code, "dq": city.code, "currentPage": page - 1}
    elif config.platform == "job51":
        params = {"keyword": keyword, "jobArea": city.code, "searchType": "2", "pageNum": page}
        if config.salary:
            params["salary"] = config.salary
    else:
        return f"https://www.zhaopin.com/sou/jl{city.code}/p{page}?" + urlencode({"kw": keyword})
    return PLATFORMS[config.platform]["entry_url"] + "?" + urlencode(params)


def is_list_api(platform, url):
    if not belongs_to(platform, url):
        return False
    path = urlparse(url).path
    return ((platform == "boss" and path == "/wapi/zpgeek/search/joblist.json")
            or (platform == "liepin" and path.endswith("/com.liepin.searchfront4c.pc-search-job"))
            or (platform == "job51" and path == "/api/job/search-pc"))


def capture_api(url):
    return any(is_list_api(platform, url) for platform in PLATFORMS) or (
        belongs_to("boss", url) and urlparse(url).path == "/wapi/zpgeek/job/detail.json")


def public_options():
    return [{"id": key, "name": value["name"], "experimental": value["experimental"], **OPTIONS[key]}
            for key, value in PLATFORMS.items()]
