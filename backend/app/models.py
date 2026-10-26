from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Literal
from .platforms import OPTIONS, PlatformId


class City(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    code: str = Field(pattern=r"^\d{1,9}$")


class CollectionConfig(BaseModel):
    platform: PlatformId = "boss"
    name: str = Field(default="", max_length=120)
    keywords: list[str] = Field(min_length=1, max_length=8)
    cities: list[City] = Field(min_length=1, max_length=8)
    max_jobs: int = Field(default=200, ge=1, le=2000)
    max_scrolls: int = Field(default=100, ge=1, le=300)
    delay_min: int = Field(default=8, ge=5, le=120)
    delay_max: int = Field(default=15, ge=5, le=180)
    salary: str = ""
    experience: str = ""
    degree: str = ""
    scale: str = ""

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, values: list[str]) -> list[str]:
        result = list(dict.fromkeys(value.strip() for value in values if value.strip()))
        if not result or any(len(value) > 80 for value in result):
            raise ValueError("请输入 1–8 个关键词，每个关键词不超过 80 字")
        return result

    @field_validator("cities")
    @classmethod
    def unique_cities(cls, values: list[City]) -> list[City]:
        return list({value.code: value for value in values}.values())

    @field_validator("salary", "experience", "degree", "scale")
    @classmethod
    def valid_filter(cls, value: str) -> str:
        if value and (not value.isdigit() or len(value) > 9):
            raise ValueError("筛选条件必须是有效的平台代码")
        return value

    @model_validator(mode="after")
    def valid_delay(self):
        if self.delay_max < self.delay_min:
            raise ValueError("最大间隔不能小于最小间隔")
        for key in ("salary", "experience", "degree", "scale"):
            value = getattr(self, key)
            if value and value not in {item["code"] for item in OPTIONS[self.platform]["filters"][key]}:
                raise ValueError("所选平台不支持该筛选条件，请重新选择")
        length = {"boss": 9, "liepin": (3, 6), "job51": 6, "zhilian": (3, 4, 5, 6)}[self.platform]
        lengths = (length,) if isinstance(length, int) else length
        if any(len(city.code) not in lengths for city in self.cities):
            raise ValueError("城市编码不属于当前平台，请重新选择城市")
        return self


class DeliveryRequest(BaseModel):
    job_ids: list[str] = Field(min_length=1, max_length=50)
    action: Literal["resume", "contact", "message"] = "resume"
    messages: dict[str, str] = Field(default_factory=dict, max_length=50)
    allow_repeat: bool = False
    confirmed: bool = False

    @model_validator(mode="after")
    def valid_request(self):
        if not self.confirmed:
            raise ValueError("请先确认岗位和投递方式")
        self.job_ids = list(dict.fromkeys(self.job_ids))
        if self.action == "message":
            if set(self.messages) != set(self.job_ids):
                raise ValueError("请为每个所选职位确认消息内容")
            self.messages = {key: value.strip() for key, value in self.messages.items()}
            if any(not value or len(value) > 1000 for value in self.messages.values()):
                raise ValueError("每条消息须为 1–1000 字")
        elif self.messages or self.allow_repeat:
            raise ValueError("消息内容和重复发送选项仅用于发送消息")
        return self


class DeliveryConfig(CollectionConfig):
    mode: Literal["delivery"] = "delivery"
    job_ids: list[str]
    delivery_action: Literal["resume", "contact", "message"]
    messages: dict[str, str] = Field(default_factory=dict)
    allow_repeat: bool = False


class DeliveryResolution(BaseModel):
    status: Literal["confirmed", "not_sent"]


class CandidateProfile(BaseModel):
    introduction: str = Field(default="", max_length=2000)
    skills: list[str] = Field(default_factory=list, max_length=40)
    roles: list[str] = Field(default_factory=list, max_length=12)
    cities: list[str] = Field(default_factory=list, max_length=12)
    years: float | None = Field(default=None, ge=0, le=60)
    degree: Literal["", "高中", "中专", "大专", "本科", "硕士", "博士"] = ""
    salary_min: float | None = Field(default=None, gt=0, le=1000)

    @field_validator("skills", "roles", "cities")
    @classmethod
    def clean_terms(cls, values):
        result = list(dict.fromkeys(v.strip() for v in values if v.strip()))
        if any(len(v) > 60 for v in result):
            raise ValueError("每项最多 60 字")
        return result


class BlacklistRule(BaseModel):
    kind: Literal["company", "title", "recruiter"] = "company"
    value: str = Field(min_length=1, max_length=200)
    company: str = Field(default="", max_length=200)
    platform: Literal["", "boss", "liepin", "job51", "zhilian"] = ""
    reason: str = Field(default="", max_length=500)
    enabled: bool = True

    @model_validator(mode="after")
    def clean_rule(self):
        self.value = self.value.strip()
        self.company = self.company.strip()
        if not self.value:
            raise ValueError("请输入黑名单内容")
        if self.kind == "recruiter" and not self.company:
            raise ValueError("招聘者规则需填写所属公司，避免同名误拦截")
        return self


class GreetingDraft(BaseModel):
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def clean_text(cls, value):
        if not value.strip():
            raise ValueError("打招呼语不能为空")
        return value.strip()
