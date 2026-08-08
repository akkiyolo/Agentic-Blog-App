from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    email: EmailStr = Field(max_length=120)


class UserCreate(UserBase):
    password:str=Field(min_length=8)


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username:str
    image_file: str | None
    image_path: str

class UserPrivate(UserPublic):
    email:EmailStr


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = Field(default=None, max_length=120)

class Token(BaseModel):
    access_token:str
    token_type:str


class PostBase(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1)


class PostCreate(PostBase):
    pass


class PostUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    content: str | None = Field(default=None, min_length=1)


class PostResponse(PostBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    date_posted: datetime
    author: UserPublic

    tags: list[str] | None = None
    summary: str | None = None
    meta_description: str | None = None
    tagging_status: str = "pending"



class PaginatedPostsResponse(BaseModel):
    posts: list[PostResponse]
    total: int
    skip: int
    limit: int
    has_more: bool


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(max_length=120)


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class PostMetadata(BaseModel):
    tags: list[str] = Field(description="3-6 concise lowercase topical tags")
    summary: str = Field(description="2-3 sentence summary of the post")
    meta_description: str = Field(description="SEO meta description, max 155 characters")


# --- Draft-assist agent schemas ---

class DraftSource(BaseModel):
    type: str  # "post" | "web"
    title: str
    url: str | None = None
    post_id: int | None = None


class DraftGenerateRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)


class DraftReviseRequest(BaseModel):
    topic: str = Field(min_length=3, max_length=200)
    feedback: str = Field(min_length=3)
    previous_outline: str
    previous_draft_title: str
    previous_draft_content: str


class DraftResponse(BaseModel):
    outline: str
    draft_title: str
    draft_content: str
    sources: list[DraftSource]


# Agent-internal structured LLM output (not an API response)
class DraftOutput(BaseModel):
    title: str = Field(description="Compelling blog post title, max 100 characters")
    content: str = Field(description="Full blog post body in plain prose")