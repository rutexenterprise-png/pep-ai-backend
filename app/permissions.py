"""Role and permission matrix for PEP AI (organisation level).

Pure Python, no framework imports, so the matrix can be unit-tested in isolation.

Model
-----
* Every organisation member has exactly one of eight roles.
* A role grants a set of permissions. Per-member overrides (grant/deny) can refine this.
* Roles that are *department scoped* (department_manager, team_leader) may only exercise
  staff.* permissions over members of their own department.
* A role may only assign / manage roles in its ASSIGNABLE_ROLES set. This prevents
  privilege escalation (nobody can create or modify someone at or above their own level,
  except the owner who may assign any role).
"""
from __future__ import annotations

ORG_OWNER = "organization_owner"
MANAGING_DIRECTOR = "managing_director"
ADMINISTRATOR = "administrator"
DEPARTMENT_MANAGER = "department_manager"
HR_MANAGER = "hr_manager"
FINANCE_MANAGER = "finance_manager"
TEAM_LEADER = "team_leader"
STANDARD_EMPLOYEE = "standard_employee"

# ordered from most to least privileged
ROLES: list[str] = [
    ORG_OWNER, MANAGING_DIRECTOR, ADMINISTRATOR, DEPARTMENT_MANAGER,
    HR_MANAGER, FINANCE_MANAGER, TEAM_LEADER, STANDARD_EMPLOYEE,
]

ROLE_LABELS = {
    ORG_OWNER: "Organisation Owner",
    MANAGING_DIRECTOR: "Managing Director",
    ADMINISTRATOR: "Administrator",
    DEPARTMENT_MANAGER: "Department Manager",
    HR_MANAGER: "Human Resources Manager",
    FINANCE_MANAGER: "Finance Manager",
    TEAM_LEADER: "Team Leader",
    STANDARD_EMPLOYEE: "Standard Employee",
}

PERMISSIONS: dict[str, str] = {
    "org.view": "View organisation details",
    "org.manage": "Change organisation settings",
    "org.transfer_ownership": "Assign or remove the Organisation Owner role",
    "workspace.view": "View workspaces",
    "workspace.create": "Create workspaces",
    "staff.directory": "See the staff directory (names, roles, departments)",
    "staff.view": "See full staff records including e-mail addresses and status",
    "staff.invite": "Invite staff by e-mail",
    "staff.update": "Edit staff department and job title",
    "staff.change_role": "Change staff roles (promote / demote)",
    "staff.suspend": "Suspend and reactivate staff",
    "staff.deactivate": "Deactivate (off-board) staff and reactivate them",
    "staff.reset_access": "Trigger an access reset for a staff member",
    "staff.activity.view": "View a staff member's activity log",
    "staff.performance.view": "View staff performance (reserved for Milestone 2 - no data/endpoint yet)",
    "department.view": "View departments",
    "department.manage": "Create, rename and delete departments",
    "permissions.configure": "Configure per-member permission overrides",
    "audit.view": "View the organisation audit log",
    "agent.manage": "Create and manage AI agent definitions",
    "workflow.manage": "Create and manage workflow definitions",
    "agent.use": "Chat with active AI agents and the built-in guide",
    "task.assign": "Assign tasks to staff and manage the tasks you assigned",
    "document.view": "View and download the organisation's documents",
    "document.manage": "Upload and delete organisation documents",
}

_ALL = frozenset(PERMISSIONS)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    ORG_OWNER: _ALL,
    MANAGING_DIRECTOR: _ALL - {"org.transfer_ownership"},
    ADMINISTRATOR: frozenset({
        "org.view", "workspace.view", "workspace.create", "staff.directory", "staff.view", "staff.invite",
        "staff.update", "staff.change_role", "staff.suspend", "staff.deactivate", "staff.reset_access",
        "staff.activity.view", "staff.performance.view", "department.view", "department.manage",
        "permissions.configure", "audit.view", "agent.manage", "workflow.manage",
        "document.view", "document.manage", "task.assign",
    }),
    DEPARTMENT_MANAGER: frozenset({
        "org.view", "workspace.view", "staff.directory", "staff.view", "staff.invite", "staff.update",
        "staff.activity.view", "staff.performance.view", "department.view",
        "document.view", "document.manage", "task.assign",
    }),
    HR_MANAGER: frozenset({
        "org.view", "workspace.view", "staff.directory", "staff.view", "staff.invite", "staff.update",
        "staff.suspend", "staff.reset_access", "staff.activity.view", "staff.performance.view", "department.view",
        "document.view", "document.manage", "task.assign",
    }),
    FINANCE_MANAGER: frozenset({"org.view", "workspace.view", "staff.directory", "department.view", "document.view", "document.manage"}),
    TEAM_LEADER: frozenset({
        "org.view", "workspace.view", "staff.directory", "staff.view", "staff.performance.view", "department.view",
        "document.view", "task.assign",
    }),
    STANDARD_EMPLOYEE: frozenset({"org.view", "workspace.view", "staff.directory", "department.view", "document.view"}),
}

# every member may chat with active agents and the guide
ROLE_PERMISSIONS = {_r: (_p | {"agent.use"}) for _r, _p in ROLE_PERMISSIONS.items()}

ASSIGNABLE_ROLES: dict[str, frozenset[str]] = {
    ORG_OWNER: frozenset(ROLES),
    MANAGING_DIRECTOR: frozenset(ROLES) - {ORG_OWNER},
    ADMINISTRATOR: frozenset({DEPARTMENT_MANAGER, HR_MANAGER, FINANCE_MANAGER, TEAM_LEADER, STANDARD_EMPLOYEE}),
    DEPARTMENT_MANAGER: frozenset({TEAM_LEADER, STANDARD_EMPLOYEE}),
    HR_MANAGER: frozenset({TEAM_LEADER, STANDARD_EMPLOYEE}),
    FINANCE_MANAGER: frozenset(),
    TEAM_LEADER: frozenset(),
    STANDARD_EMPLOYEE: frozenset(),
}

DEPARTMENT_SCOPED_ROLES = frozenset({DEPARTMENT_MANAGER, TEAM_LEADER})
SCOPED_PERMISSION_PREFIX = "staff."
# permissions that overrides may never grant
NON_GRANTABLE = frozenset({"org.transfer_ownership", "permissions.configure"})

# Original package roles -> new roles (compatibility with legacy endpoints and migration)
LEGACY_ROLE_MAP = {
    "owner": ORG_OWNER,
    "administrator": ADMINISTRATOR,
    "manager": DEPARTMENT_MANAGER,
    "operator": STANDARD_EMPLOYEE,
    "viewer": STANDARD_EMPLOYEE,
}


def normalise_role(role: str) -> str | None:
    """Accept new role keys and legacy role names; return the canonical role or None."""
    if role in ROLE_PERMISSIONS:
        return role
    return LEGACY_ROLE_MAP.get(role)


def effective_permissions(role: str, granted=None, denied=None) -> frozenset[str]:
    base = set(ROLE_PERMISSIONS.get(role, frozenset()))
    if role != ORG_OWNER:  # the owner's permissions can never be reduced or extended
        base |= {p for p in (granted or []) if p in PERMISSIONS and p not in NON_GRANTABLE}
        base -= {p for p in (denied or []) if p in PERMISSIONS}
    return frozenset(base)


def can_assign_role(actor_role: str, target_role: str) -> bool:
    return target_role in ASSIGNABLE_ROLES.get(actor_role, frozenset())


def is_department_scoped(role: str) -> bool:
    return role in DEPARTMENT_SCOPED_ROLES


def can_manage_member(actor_role: str, actor_department_id: int | None,
                      target_role: str, target_department_id: int | None) -> bool:
    """May the actor perform staff administration on this target?

    (The caller additionally checks the specific permission and that actor != target.)
    """
    if not can_assign_role(actor_role, target_role):
        return False
    if is_department_scoped(actor_role):
        return actor_department_id is not None and actor_department_id == target_department_id
    return True


def role_catalogue() -> list[dict]:
    return [
        {
            "role": r,
            "label": ROLE_LABELS[r],
            "department_scoped": r in DEPARTMENT_SCOPED_ROLES,
            "permissions": sorted(ROLE_PERMISSIONS[r]),
            "can_assign_roles": [x for x in ROLES if x in ASSIGNABLE_ROLES[r]],
        }
        for r in ROLES
    ]
