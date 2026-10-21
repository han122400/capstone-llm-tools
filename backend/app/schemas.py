from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .email_input import EmailEnvelope


class Sample(BaseModel):
    model_config = ConfigDict(extra='forbid')
    sample_id: str = Field(min_length=1, max_length=120)
    subject: str = Field(default='', max_length=4096)
    body: str = Field(default='', max_length=300000)
    label: Literal['NORMAL', 'INJECTION']
    language: str = Field(default='ko', max_length=30)
    category: str = Field(default='unspecified', max_length=150)
    synthetic: bool | None = None
    created_at: str | None = None
    notes: str = Field(default='', max_length=5000)
    template_family: str = Field(default='', max_length=150)
    source_dataset: str | None = Field(default=None, max_length=150)
    source_dataset_name: str | None = Field(default=None, max_length=500)
    source_url: str | None = Field(default=None, max_length=2000)
    source_version: str | None = Field(default=None, max_length=300)
    source_sample_id: str | None = Field(default=None, max_length=300)
    source_file: str | None = Field(default=None, max_length=1000)
    source_record_index: int | None = Field(default=None, ge=0)
    source_line: int | None = Field(default=None, ge=1)
    source_data_version: str | None = None
    source_file_hash: str | None = None
    source_download_url: str | None = None
    source_context: dict | None = None
    pair_id: str | None = Field(default=None, max_length=300)
    transformation_notes: str | None = Field(default=None, max_length=5000)
    transformation_version: str | None = None
    body_hash: str | None = None
    body_hash_method: str | None = None
    email: EmailEnvelope | None = None

    @field_validator('sample_id')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('빈 문자열을 사용할 수 없습니다')
        return value

    @model_validator(mode='after')
    def coherent_content(self):
        if self.email:
            content = self.email.content
            for field, value in (('subject', content.subject or ''), ('body', content.analysis_text)):
                if getattr(self, field) and getattr(self, field) != value:
                    raise ValueError(f'{field}와 공통 이메일 입력이 다릅니다. email.content를 함께 수정하세요')
                setattr(self, field, value)
        elif not self.subject.strip() or not self.body.strip():
            raise ValueError('기존 형식은 제목과 본문이 필요합니다')
        return self


class DatasetInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=150)
    split: Literal['development', 'evaluation'] = 'development'
    samples: list[Sample] = Field(min_length=1, max_length=5000)
    manifest: dict | None = None

    @model_validator(mode='after')
    def unique(self):
        ids = [x.sample_id for x in self.samples]
        if len(ids) != len(set(ids)):
            raise ValueError('sample_id는 데이터셋 안에서 고유해야 합니다')
        if not self.name.strip():
            raise ValueError('데이터셋 이름이 필요합니다')
        return self


class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    dataset_id: str
    configs: list[Literal['foundation_sec','qwen','jev','foundation_sec_then_jev','qwen_then_jev']] = Field(min_length=1, max_length=5)
    mode: Literal['reuse','live'] = 'reuse'
    demo: bool = False
    explanations: bool = False
    warmup: bool = False
    external_transfer_confirmed: bool = False

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.configs)) != len(self.configs):
            raise ValueError('구성 중복 선택')
        return self


class ImportInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=150)
    split: Literal['development','evaluation'] | None = None
    format: Literal['json','csv']
    content: str = Field(max_length=10_000_000)


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ollama_url: str | None = None
    foundation_sec_model: str | None = Field(default=None, max_length=250)
    qwen_model: str | None = Field(default=None, max_length=250)
    qwen_thinking: bool | None = Field(default=None, strict=True)
    jev_model: str | None = Field(default=None, max_length=250)
    context_length: int | None = Field(default=None, ge=4096, le=65536)
    temperature: float | None = Field(default=None, ge=0, le=2)
    seed: int | None = Field(default=None, ge=0, le=2147483647)
    max_output_tokens: int | None = Field(default=None, ge=16, le=8192)
    timeout_seconds: int | None = Field(default=None, ge=1, le=600)
    max_attempts: int | None = Field(default=None, ge=1, le=3)

    @field_validator('ollama_url')
    @classmethod
    def local_only(cls, value):
        if value is not None:
            from urllib.parse import urlparse
            parsed = urlparse(value)
            if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
                raise ValueError('Ollama 주소는 인증 정보 없는 로컬 HTTP 주소여야 합니다')
            return value.rstrip('/')
        return value
