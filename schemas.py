from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from .security import validate_password_strength


# ------------------------------------------------------------------ auth
class RegisterIn(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def _strength(self):
        problems = validate_password_strength(self.password, str(self.email), self.full_name)
        if problems:
            raise ValueError("; ".join(problems))
        return self


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None  # additive in Milestone 1
    refresh_expires_in: int | None = None


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    email_verified: bool = False
    model_config = ConfigDict(from_attributes=True)


class RefreshIn(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=200)


class TokenIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)


class EmailIn(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v):
        problems = validate_password_strength(v)
        if problems:
            raise ValueError("; ".join(problems))
        return v


class ChangePasswordIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strength(cls, v):
        problems = validate_password_strength(v)
        if problems:
            raise ValueError("; ".join(problems))
        return v


class SessionOut(BaseModel):
    id: int
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime
    ip: str | None
    user_agent: str | None
    current: bool = False


# ------------------------------------------------------------------ workspaces (legacy + new)
class WorkspaceCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    workspace_name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=100)


class WorkspaceOut(BaseModel):
    id: int
    organization_id: int
    name: str
    role: str
    model_config = ConfigDict(from_attributes=True)


class MemberCreate(BaseModel):
    """Legacy add-member body. Accepts the original roles and the new role keys."""
    email: EmailStr
    role: str = Field(pattern=r"^(administrator|manager|operator|viewer|managing_director|department_manager|hr_manager|finance_manager|team_leader|standard_employee)$")


# ------------------------------------------------------------------ organisations
class OrgCreate(BaseModel):
    organization_name: str = Field(min_length=2, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=2, max_length=100)
    workspace_name: str = Field(default="Head Office", min_length=2, max_length=200)


class OrgOut(BaseModel):
    id: int
    name: str
    slug: str
    status: str
    my_role: str
    my_status: str


class MeInOrg(BaseModel):
    member_id: int
    role: str
    role_label: str
    status: str
    department_id: int | None
    department_scoped: bool
    permissions: list[str]


class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class DepartmentOut(BaseModel):
    id: int
    name: str
    description: str | None
    member_count: int = 0


class MemberOut(BaseModel):
    id: int  # organisation member id
    user_id: int
    full_name: str
    email: str | None = None  # only with staff.view
    role: str
    role_label: str
    status: str | None = None  # only with staff.view
    department_id: int | None
    department_name: str | None
    job_title: str | None
    joined_at: datetime | None = None
    granted_permissions: list[str] | None = None
    denied_permissions: list[str] | None = None


class MemberUpdate(BaseModel):
    role: str | None = None
    department_id: int | None = None
    job_title: str | None = Field(default=None, max_length=120)


class ReasonIn(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class PermissionsUpdate(BaseModel):
    grant: list[str] = Field(default_factory=list, max_length=50)
    deny: list[str] = Field(default_factory=list, max_length=50)


class InviteIn(BaseModel):
    email: EmailStr
    role: str
    department_id: int | None = None


class InviteOut(BaseModel):
    id: int
    email: str
    role: str
    department_id: int | None
    status: str  # pending|accepted|revoked|expired
    email_status: str
    created_at: datetime
    expires_at: datetime
    invite_link: str | None = None  # returned once, to the inviter only, on create / resend


class InvitePreviewOut(BaseModel):
    organization_name: str
    email: str
    role: str
    role_label: str


class AuditOut(BaseModel):
    id: int
    created_at: datetime
    action: str
    actor_user_id: int | None
    actor_name: str | None = None
    target_type: str | None
    target_id: str | None
    detail: dict | None
    ip: str | None


# ------------------------------------------------------------- AI workforce definitions
class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    agent_type: str = Field(default="custom", min_length=2, max_length=60)
    instructions: str = Field(min_length=1, max_length=12000)
    model_provider: str = Field(default="not_configured", max_length=40)
    model_name: str | None = Field(default=None, max_length=100)
    settings: dict = Field(default_factory=dict)

    @field_validator("name", "agent_type", "instructions", "model_provider")
    @classmethod
    def strip_required_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    agent_type: str | None = Field(default=None, min_length=2, max_length=60)
    instructions: str | None = Field(default=None, min_length=1, max_length=12000)
    model_provider: str | None = Field(default=None, max_length=40)
    model_name: str | None = Field(default=None, max_length=100)
    settings: dict | None = None
    status: str | None = None

    @model_validator(mode="after")
    def required_update_fields_not_null(self):
        for field in ("name", "agent_type", "instructions", "model_provider", "settings"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    @field_validator("status")
    @classmethod
    def valid_agent_status(cls, value):
        if value is not None and value not in {"draft", "active", "paused"}:
            raise ValueError("Status must be draft, active or paused")
        return value


class AgentOut(BaseModel):
    id: int
    organization_id: int
    name: str
    description: str | None
    agent_type: str
    instructions: str
    model_provider: str
    model_name: str | None
    status: str
    settings: dict
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    definition: dict = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def strip_workflow_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Workflow name cannot be blank")
        return value


class WorkflowUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    definition: dict | None = None
    status: str | None = None

    @model_validator(mode="after")
    def required_update_fields_not_null(self):
        for field in ("name", "definition"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self

    @field_validator("status")
    @classmethod
    def valid_workflow_status(cls, value):
        if value is not None and value not in {"draft", "active", "paused"}:
            raise ValueError("Status must be draft, active or paused")
        return value


class WorkflowOut(BaseModel):
    id: int
    organization_id: int
    name: str
    description: str | None
    status: str
    definition: dict
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DocumentOut(BaseModel):
    id: int
    organization_id: int
    filename: str
    content_type: str
    size_bytes: int
    description: str | None
    uploaded_by_user_id: int | None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# ------------------------------------------------------------------ tasks & analytics
TASK_STATUSES = {"todo", "in_progress", "done", "cancelled"}


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    assignee_member_id: int
    priority: str = "normal"
    due_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Title is too short")
        return value

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, value):
        if value not in {"low", "normal", "high"}:
            raise ValueError("Priority must be low, normal or high")
        return value


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    assignee_member_id: int | None = None
    priority: str | None = None
    due_at: datetime | None = None
    status: str | None = None
    completion_note: str | None = Field(default=None, max_length=1000)

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value is not None and value not in TASK_STATUSES:
            raise ValueError("Status must be todo, in_progress, done or cancelled")
        return value

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, value):
        if value is not None and value not in {"low", "normal", "high"}:
            raise ValueError("Priority must be low, normal or high")
        return value


class TaskOut(BaseModel):
    id: int
    organization_id: int
    title: str
    description: str | None
    assignee_member_id: int
    assignee_name: str | None = None
    assigned_by_user_id: int | None
    status: str
    priority: str
    due_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    completion_note: str | None
    overdue: bool = False
    created_at: datetime
    updated_at: datetime


class PhoneIn(BaseModel):
    phone: str | None = Field(default=None, max_length=32)


class StaffEfficiencyRow(BaseModel):
    member_id: int
    full_name: str
    department_name: str | None
    assigned: int
    completed: int
    on_time: int
    open_overdue: int
    completion_rate: float | None
    on_time_rate: float | None
    avg_hours_to_complete: float | None
    score: int | None
    rating: str
