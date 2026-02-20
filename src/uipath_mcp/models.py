"""
Pydantic v2 models for UiPath Orchestrator API responses.

Design decisions:
  - OrchestratorModel base: populate_by_name=True (accept both alias & field name),
    extra="ignore" (unknown API fields silently dropped).
  - All fields use Field(alias="PascalCase") to match the API response keys.
  - Optional fields default to None — OData responses often omit null fields.
  - Enums use str mixin so JSON serialisation works without extra config.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


T = TypeVar("T")


# ── Base model ─────────────────────────────────────────────────────────────────

class OrchestratorModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )


# ── Enums ──────────────────────────────────────────────────────────────────────

class JobState(str, Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    STOPPING = "Stopping"
    TERMINATING = "Terminating"
    FAULTED = "Faulted"
    SUCCESSFUL = "Successful"
    STOPPED = "Stopped"
    SUSPENDED = "Suspended"
    RESUMED = "Resumed"


class JobSource(str, Enum):
    MANUAL = "Manual"
    SCHEDULE = "Schedule"
    QUEUE = "Queue"
    EXTERNAL = "ExternalJob"
    API = "Api"
    AGENT = "Agent"


class RobotState(str, Enum):
    AVAILABLE = "Available"
    BUSY = "Busy"
    DISCONNECTED = "Disconnected"
    UNRESPONSIVE = "Unresponsive"
    FAULTED = "Faulted"


class QueueItemStatus(str, Enum):
    NEW = "New"
    IN_PROGRESS = "InProgress"
    FAILED = "Failed"
    SUCCESSFUL = "Successful"
    ABANDONED = "Abandoned"
    RETRIED = "Retried"
    DELETED = "Deleted"


class QueueItemPriority(str, Enum):
    LOW = "Low"
    NORMAL = "Normal"
    HIGH = "High"


class AssetValueType(str, Enum):
    TEXT = "Text"
    INTEGER = "Integer"
    BOOLEAN = "Bool"
    CREDENTIAL = "Credential"


class ReleaseStrategy(str, Enum):
    ALL = "All"
    SPECIFIC = "Specific"
    JOB_COUNT = "JobsCount"
    ROBOT_COUNT = "RobotCount"


class StopStrategy(str, Enum):
    SOFT_STOP = "SoftStop"
    KILL = "Kill"


# ── Job models ─────────────────────────────────────────────────────────────────

class Job(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    key: str | None = Field(default=None, alias="Key")
    release_name: str | None = Field(default=None, alias="ReleaseName")
    release_key: str | None = Field(default=None, alias="ReleaseKey")
    state: JobState | None = Field(default=None, alias="State")
    source: str | None = Field(default=None, alias="Source")
    start_time: datetime | None = Field(default=None, alias="StartTime")
    end_time: datetime | None = Field(default=None, alias="EndTime")
    creation_time: datetime | None = Field(default=None, alias="CreationTime")
    robot_name: str | None = Field(default=None, alias="Robot")
    host_machine_name: str | None = Field(default=None, alias="HostMachineName")
    info: str | None = Field(default=None, alias="Info")
    input_arguments: str | None = Field(default=None, alias="InputArguments")
    output_arguments: str | None = Field(default=None, alias="OutputArguments")
    folder_id: int | None = Field(default=None, alias="OrganizationUnitId")
    folder_name: str | None = Field(default=None, alias="OrganizationUnitFullyQualifiedName")


# ── Queue models ───────────────────────────────────────────────────────────────

class Queue(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    name: str | None = Field(default=None, alias="Name")
    description: str | None = Field(default=None, alias="Description")
    max_number_of_retries: int | None = Field(default=None, alias="MaxNumberOfRetries")
    accept_automatically_retry: bool | None = Field(default=None, alias="AcceptAutomaticallyRetry")
    enforce_unique_reference: bool | None = Field(default=None, alias="EnforceUniqueReference")
    creation_time: datetime | None = Field(default=None, alias="CreationTime")
    successful_transactions_count: int | None = Field(default=None, alias="SuccessfulTransactionCount")
    failed_transactions_count: int | None = Field(default=None, alias="FailedTransactionCount")
    in_progress_count: int | None = Field(default=None, alias="InProgressTransactionCount")


class QueueItem(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    queue_definition_id: int | None = Field(default=None, alias="QueueDefinitionId")
    queue_definition_name: str | None = Field(default=None, alias="QueueDefinitionName")
    status: QueueItemStatus | None = Field(default=None, alias="Status")
    review_status: str | None = Field(default=None, alias="ReviewStatus")
    priority: QueueItemPriority | None = Field(default=None, alias="Priority")
    reference: str | None = Field(default=None, alias="Reference")
    defer_date: datetime | None = Field(default=None, alias="DeferDate")
    due_date: datetime | None = Field(default=None, alias="DueDate")
    creation_time: datetime | None = Field(default=None, alias="CreationTime")
    start_time: datetime | None = Field(default=None, alias="StartTime")
    end_time: datetime | None = Field(default=None, alias="EndTime")
    retry_number: int | None = Field(default=None, alias="RetryNumber")
    specific_content: dict[str, Any] | None = Field(default=None, alias="SpecificContent")
    output: dict[str, Any] | None = Field(default=None, alias="Output")
    analytics_data: dict[str, Any] | None = Field(default=None, alias="AnalyticsData")
    exception_type: str | None = Field(default=None, alias="ProcessingExceptionType")
    exception_reason: str | None = Field(default=None, alias="ProcessingExceptionReason")
    robot_name: str | None = Field(default=None, alias="Robot")


# ── Robot models ───────────────────────────────────────────────────────────────

class Robot(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    name: str | None = Field(default=None, alias="Name")
    machine_name: str | None = Field(default=None, alias="MachineName")
    machine_id: int | None = Field(default=None, alias="MachineId")
    type: str | None = Field(default=None, alias="Type")
    username: str | None = Field(default=None, alias="Username")
    description: str | None = Field(default=None, alias="Description")
    version: str | None = Field(default=None, alias="Version")
    last_modification_time: datetime | None = Field(default=None, alias="LastModificationTime")
    provisioned_licenses: int | None = Field(default=None, alias="ProvisionedLicenses")


class RobotSession(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    robot_id: int | None = Field(default=None, alias="RobotId")
    machine_id: int | None = Field(default=None, alias="MachineId")
    machine_name: str | None = Field(default=None, alias="MachineName")
    host_machine_name: str | None = Field(default=None, alias="HostMachineName")
    state: RobotState | None = Field(default=None, alias="State")
    reporting_time: datetime | None = Field(default=None, alias="ReportingTime")
    is_connected: bool | None = Field(default=None, alias="IsConnected")


# ── Machine models ─────────────────────────────────────────────────────────────

class Machine(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    key: str | None = Field(default=None, alias="Key")
    name: str | None = Field(default=None, alias="Name")
    type: str | None = Field(default=None, alias="Type")
    description: str | None = Field(default=None, alias="Description")
    non_production_slots: int | None = Field(default=None, alias="NonProductionSlots")
    unattended_slots: int | None = Field(default=None, alias="UnattendedSlots")
    headless_slots: int | None = Field(default=None, alias="HeadlessSlots")
    testing_slots: int | None = Field(default=None, alias="TestingSlots")


# ── Asset models ───────────────────────────────────────────────────────────────

class Asset(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    name: str | None = Field(default=None, alias="Name")
    canonical_name: str | None = Field(default=None, alias="CanonicalName")
    value_type: AssetValueType | None = Field(default=None, alias="ValueType")
    value_scope: str | None = Field(default=None, alias="ValueScope")
    string_value: str | None = Field(default=None, alias="StringValue")
    bool_value: bool | None = Field(default=None, alias="BoolValue")
    integer_value: int | None = Field(default=None, alias="IntValue")
    credential_username: str | None = Field(default=None, alias="CredentialUsername")
    # CredentialPassword is NEVER returned by the API — security by design
    description: str | None = Field(default=None, alias="Description")
    folder_id: int | None = Field(default=None, alias="OrganizationUnitId")


# ── Release / Process models ───────────────────────────────────────────────────

class Release(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    key: str | None = Field(default=None, alias="Key")
    process_key: str | None = Field(default=None, alias="ProcessKey")
    process_version: str | None = Field(default=None, alias="ProcessVersion")
    is_latest_version: bool | None = Field(default=None, alias="IsLatestVersion")
    description: str | None = Field(default=None, alias="Description")
    name: str | None = Field(default=None, alias="Name")
    entry_point_path: str | None = Field(default=None, alias="EntryPointPath")
    input_arguments: str | None = Field(default=None, alias="InputArguments")
    job_priority: str | None = Field(default=None, alias="JobPriority")
    environment_name: str | None = Field(default=None, alias="EnvironmentName")


# ── Schedule models ────────────────────────────────────────────────────────────

class ProcessSchedule(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    name: str | None = Field(default=None, alias="Name")
    release_name: str | None = Field(default=None, alias="ReleaseName")
    release_id: int | None = Field(default=None, alias="ReleaseId")
    enabled: bool | None = Field(default=None, alias="Enabled")
    time_zone_id: str | None = Field(default=None, alias="TimeZoneId")
    cron_expression: str | None = Field(default=None, alias="CronExpression")
    start_at: datetime | None = Field(default=None, alias="StartAt")
    next_execution: datetime | None = Field(default=None, alias="NextExecution")
    strategy: ReleaseStrategy | None = Field(default=None, alias="Strategy")
    stop_strategy: str | None = Field(default=None, alias="StopStrategy")


# ── Audit log models ───────────────────────────────────────────────────────────

class AuditLog(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    user_name: str | None = Field(default=None, alias="UserName")
    user_id: int | None = Field(default=None, alias="UserId")
    action: str | None = Field(default=None, alias="Action")
    entity_type: str | None = Field(default=None, alias="EntityType")
    creation_time: datetime | None = Field(default=None, alias="CreationTime")
    component: str | None = Field(default=None, alias="Component")
    service_name: str | None = Field(default=None, alias="ServiceName")
    operation: str | None = Field(default=None, alias="Operation")


class RobotLog(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    level: str | None = Field(default=None, alias="Level")
    windows_identity: str | None = Field(default=None, alias="WindowsIdentity")
    process_name: str | None = Field(default=None, alias="ProcessName")
    time_stamp: datetime | None = Field(default=None, alias="TimeStamp")
    message: str | None = Field(default=None, alias="Message")
    job_key: str | None = Field(default=None, alias="JobKey")
    raw_message: str | None = Field(default=None, alias="RawMessage")
    robot_name: str | None = Field(default=None, alias="RobotName")
    machine_name: str | None = Field(default=None, alias="MachineName")


# ── Folder models ──────────────────────────────────────────────────────────────

class Folder(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    key: str | None = Field(default=None, alias="Key")
    display_name: str | None = Field(default=None, alias="DisplayName")
    fully_qualified_name: str | None = Field(default=None, alias="FullyQualifiedName")
    parent_id: int | None = Field(default=None, alias="ParentId")
    description: str | None = Field(default=None, alias="Description")
    provisioning_type: str | None = Field(default=None, alias="ProvisioningType")
    permission_model: str | None = Field(default=None, alias="PermissionModel")


# ── Webhook models ─────────────────────────────────────────────────────────────

class Webhook(OrchestratorModel):
    id: int | None = Field(default=None, alias="Id")
    name: str | None = Field(default=None, alias="Name")
    url: str | None = Field(default=None, alias="Url")
    enabled: bool | None = Field(default=None, alias="Enabled")
    secret: str | None = Field(default=None, alias="Secret")
    allow_insecure_ssl: bool | None = Field(default=None, alias="AllowInsecureSsl")
    subscribe_to_all_events: bool | None = Field(default=None, alias="SubscribeToAllEvents")
    events: list[dict[str, Any]] | None = Field(default=None, alias="Events")
    creation_time: datetime | None = Field(default=None, alias="CreationTime")


# ── OData collection wrapper ───────────────────────────────────────────────────

class ODataPage(BaseModel, Generic[T]):
    """Generic wrapper for OData collection responses."""

    model_config = ConfigDict(populate_by_name=True)

    count: int | None = Field(default=None, alias="@odata.count")
    next_link: str | None = Field(default=None, alias="@odata.nextLink")
    value: list[T] = Field(default_factory=list)
