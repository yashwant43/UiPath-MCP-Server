"""
Job management tools — 12 tools.

  list_jobs          list_running_jobs  list_failed_jobs  list_jobs_by_process
  get_job            get_job_output     get_job_statistics get_job_logs
  start_job          stop_job           bulk_stop_jobs     wait_for_job  ⭐new
"""

from __future__ import annotations

import asyncio
import json
from typing import Annotated, Any

from mcp.server.fastmcp import Context, FastMCP
from pydantic import Field

from ..client import ODataParams, UiPathError
from ..models import Job, JobState, ReleaseStrategy


def _state(ctx: Context) -> Any:
    return ctx.request_context.lifespan_context


def register(mcp: FastMCP, read_only: bool = False) -> None:

    # ── list_jobs ─────────────────────────────────────────────────────────────

    @mcp.tool()
    async def list_jobs(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder/Organization Unit ID")] = None,
        state: Annotated[
            str | None,
            Field(description="Filter by state: Pending | Running | Faulted | Successful | Stopped"),
        ] = None,
        process_name: Annotated[
            str | None, Field(description="Filter by release/process name (partial match)")
        ] = None,
        top: Annotated[int, Field(description="Max results to return", ge=1, le=1000)] = 50,
        skip: Annotated[int, Field(description="Records to skip (pagination)", ge=0)] = 0,
        order_desc: Annotated[bool, Field(description="Sort by CreationTime descending")] = True,
    ) -> str:
        """List jobs with optional state/process filters and pagination."""
        st = _state(ctx)
        try:
            filters: list[str] = []
            if state:
                filters.append(
                    f"State eq UiPath.Server.Configuration.OData.JobState'{state}'"
                )
            if process_name:
                filters.append(f"contains(ReleaseName,'{process_name}')")

            params = (
                ODataParams()
                .top(top)
                .skip(skip)
                .count()
                .orderby("CreationTime", "desc" if order_desc else "asc")
            )
            if filters:
                params.filter(" and ".join(filters))

            data = await st.client.get("Jobs", params=params.build(), folder_id=folder_id)
            jobs = [Job.model_validate(j).model_dump() for j in data.get("value", [])]
            return json.dumps(
                {"total_count": data.get("@odata.count", len(jobs)), "skip": skip, "jobs": jobs},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── list_running_jobs ─────────────────────────────────────────────────────

    @mcp.tool()
    async def list_running_jobs(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """Shortcut: list only currently running jobs."""
        st = _state(ctx)
        try:
            params = (
                ODataParams()
                .top(top)
                .count()
                .filter("State eq UiPath.Server.Configuration.OData.JobState'Running'")
                .orderby("StartTime", "desc")
            )
            data = await st.client.get("Jobs", params=params.build(), folder_id=folder_id)
            jobs = [Job.model_validate(j).model_dump() for j in data.get("value", [])]
            return json.dumps({"running_count": len(jobs), "jobs": jobs}, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── list_failed_jobs ──────────────────────────────────────────────────────

    @mcp.tool()
    async def list_failed_jobs(
        ctx: Context,
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        since: Annotated[
            str | None,
            Field(description="ISO 8601 start date e.g. 2024-01-01T00:00:00Z"),
        ] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 50,
    ) -> str:
        """Shortcut: list faulted jobs, optionally since a given date."""
        st = _state(ctx)
        try:
            parts = ["State eq UiPath.Server.Configuration.OData.JobState'Faulted'"]
            if since:
                parts.append(f"CreationTime ge datetime'{since.rstrip('Z')}'")
            params = (
                ODataParams()
                .top(top)
                .count()
                .filter(" and ".join(parts))
                .orderby("CreationTime", "desc")
            )
            data = await st.client.get("Jobs", params=params.build(), folder_id=folder_id)
            jobs = [Job.model_validate(j).model_dump() for j in data.get("value", [])]
            return json.dumps({"failed_count": len(jobs), "jobs": jobs}, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── list_jobs_by_process ──────────────────────────────────────────────────

    @mcp.tool()
    async def list_jobs_by_process(
        ctx: Context,
        process_name: Annotated[str, Field(description="Exact process/release name")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> str:
        """List all jobs for a specific process name (exact match)."""
        st = _state(ctx)
        try:
            params = (
                ODataParams()
                .top(top)
                .count()
                .filter(f"ReleaseName eq '{process_name}'")
                .orderby("CreationTime", "desc")
            )
            data = await st.client.get("Jobs", params=params.build(), folder_id=folder_id)
            jobs = [Job.model_validate(j).model_dump() for j in data.get("value", [])]
            return json.dumps(
                {"process_name": process_name, "total_count": data.get("@odata.count"), "jobs": jobs},
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── get_job ───────────────────────────────────────────────────────────────

    @mcp.tool()
    async def get_job(
        ctx: Context,
        job_id: Annotated[int, Field(description="Job ID")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """Get full details of a single job by ID."""
        st = _state(ctx)
        try:
            data = await st.client.get_by_id("Jobs", job_id, folder_id=folder_id)
            return json.dumps(Job.model_validate(data).model_dump(), default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── get_job_output ────────────────────────────────────────────────────────

    @mcp.tool()
    async def get_job_output(
        ctx: Context,
        job_id: Annotated[int, Field(description="Job ID")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
    ) -> str:
        """
        Get the output arguments of a completed job.
        Returns both the raw JSON string and parsed dict for convenience.
        """
        st = _state(ctx)
        try:
            data = await st.client.get_by_id("Jobs", job_id, folder_id=folder_id)
            job = Job.model_validate(data)
            result: dict[str, Any] = {
                "job_id": job_id,
                "state": job.state,
                "output_arguments_raw": job.output_arguments,
            }
            if job.output_arguments:
                try:
                    result["output_arguments"] = json.loads(job.output_arguments)
                except json.JSONDecodeError:
                    result["output_arguments"] = None
            return json.dumps(result, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── get_job_statistics ────────────────────────────────────────────────────

    @mcp.tool()
    async def get_job_statistics(
        ctx: Context,
        process_name: Annotated[str, Field(description="Process/release name")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        since: Annotated[str | None, Field(description="ISO 8601 start date")] = None,
        top: Annotated[int, Field(ge=1, le=5000)] = 500,
    ) -> str:
        """
        Calculate job success/failure statistics for a given process.
        Returns counts per state (Successful, Faulted, Stopped, etc.).
        """
        st = _state(ctx)
        try:
            parts = [f"ReleaseName eq '{process_name}'"]
            if since:
                parts.append(f"CreationTime ge datetime'{since.rstrip('Z')}'")
            params = (
                ODataParams()
                .top(top)
                .filter(" and ".join(parts))
                .select("Id", "State", "StartTime", "EndTime")
            )
            data = await st.client.get("Jobs", params=params.build(), folder_id=folder_id)
            jobs_raw = data.get("value", [])

            counts: dict[str, int] = {}
            for j in jobs_raw:
                state = j.get("State", "Unknown")
                counts[state] = counts.get(state, 0) + 1

            total = len(jobs_raw)
            successful = counts.get("Successful", 0)
            faulted = counts.get("Faulted", 0)
            success_rate = round(successful / total * 100, 1) if total else 0.0

            return json.dumps(
                {
                    "process_name": process_name,
                    "total_jobs": total,
                    "success_rate_pct": success_rate,
                    "counts_by_state": counts,
                },
                default=str,
            )
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── get_job_logs ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def get_job_logs(
        ctx: Context,
        job_key: Annotated[str, Field(description="Job Key (GUID, not numeric ID)")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        level: Annotated[
            str | None,
            Field(description="Filter by level: Trace | Info | Warn | Error | Fatal"),
        ] = None,
        top: Annotated[int, Field(ge=1, le=1000)] = 100,
    ) -> str:
        """Retrieve execution logs for a specific job (identified by job Key GUID)."""
        st = _state(ctx)
        try:
            # Step 1: look up the job by Key to get process name + time window.
            # RobotLogs does not support $filter=JobKey eq guid'...' in OData,
            # so we filter by process name + time range in OData, then narrow in Python.
            job_data = await st.client.get(
                "Jobs",
                params=ODataParams().filter(f"Key eq guid'{job_key}'").top(1).build(),
                folder_id=folder_id,
            )
            jobs = job_data.get("value", [])

            parts: list[str] = []
            if jobs:
                job = jobs[0]
                if job.get("ReleaseName"):
                    parts.append(f"ProcessName eq '{job['ReleaseName']}'")
                if job.get("StartTime"):
                    ts = str(job["StartTime"]).rstrip("Z")
                    parts.append(f"TimeStamp ge datetime'{ts}'")
                if job.get("EndTime"):
                    te = str(job["EndTime"]).rstrip("Z")
                    parts.append(f"TimeStamp le datetime'{te}'")

            if level:
                parts.append(f"Level eq '{level}'")

            params = ODataParams().top(top).orderby("TimeStamp", "asc")
            if parts:
                params.filter(" and ".join(parts))

            data = await st.client.get("RobotLogs", params=params.build(), folder_id=folder_id)
            logs = data.get("value", [])

            # Narrow to exact job key in Python (handles shared-process overlap)
            logs = [l for l in logs if l.get("JobKey") == job_key]

            return json.dumps({"count": len(logs), "logs": logs}, default=str)
        except UiPathError as e:
            return json.dumps(e.to_dict())

    # ── start_job / stop_job / bulk_stop_jobs (write — omitted in read_only mode) ─

    if not read_only:

        @mcp.tool()
        async def start_job(
            ctx: Context,
            process_name: Annotated[str, Field(description="Process/release name to start")],
            folder_id: Annotated[int | None, Field(description="Folder ID where the process lives")] = None,
            input_arguments: Annotated[
                dict[str, Any] | None,
                Field(description='Input arguments as JSON object e.g. {"InputPath": "C:/data"}'),
            ] = None,
            strategy: Annotated[
                str,
                Field(description="Allocation strategy: All | Specific | JobsCount | RobotCount"),
            ] = "All",
            robot_ids: Annotated[
                list[int] | None, Field(description="Specific robot IDs (required when strategy=Specific)")
            ] = None,
            jobs_count: Annotated[
                int | None, Field(description="Number of job instances (used with JobsCount strategy)")
            ] = None,
        ) -> str:
            """
            Start a new job for a process.
            Step 1: Looks up the release key by process name.
            Step 2: Starts the job using the release key.
            Returns the list of created jobs with their IDs and initial states.
            """
            st = _state(ctx)
            try:
                releases_data = await st.client.get(
                    "Releases",
                    params=ODataParams().filter(f"Name eq '{process_name}'").top(1).build(),
                    folder_id=folder_id,
                )
                releases = releases_data.get("value", [])
                if not releases:
                    return json.dumps(
                        {"error": f"Process '{process_name}' not found in folder {folder_id}"}
                    )
                release_key: str = releases[0]["Key"]
                start_info: dict[str, Any] = {
                    "ReleaseKey": release_key,
                    "Strategy": strategy,
                    "Source": "Manual",
                }
                if robot_ids:
                    start_info["RobotIds"] = robot_ids
                if jobs_count is not None:
                    start_info["JobsCount"] = jobs_count
                if input_arguments:
                    start_info["InputArguments"] = json.dumps(input_arguments)
                result = await st.client.post(
                    "Jobs",
                    body={"startInfo": start_info},
                    action="StartJobs",
                    folder_id=folder_id,
                )
                started = [Job.model_validate(j).model_dump() for j in result.get("value", [])]
                return json.dumps(
                    {"message": f"Started {len(started)} job(s) for '{process_name}'", "jobs": started},
                    default=str,
                )
            except UiPathError as e:
                return json.dumps(e.to_dict())

        @mcp.tool()
        async def stop_job(
            ctx: Context,
            job_id: Annotated[int, Field(description="Job ID to stop")],
            folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
            strategy: Annotated[
                str, Field(description="SoftStop (graceful) or Kill (immediate)")
            ] = "SoftStop",
        ) -> str:
            """Stop a running or pending job."""
            st = _state(ctx)
            try:
                body = {"jobId": job_id, "strategy": strategy}
                await st.client.post("Jobs", body=body, action="StopJob", folder_id=folder_id)
                return json.dumps({"message": f"Stop ({strategy}) requested for job {job_id}"})
            except UiPathError as e:
                return json.dumps(e.to_dict())

        @mcp.tool()
        async def bulk_stop_jobs(
            ctx: Context,
            job_ids: Annotated[list[int], Field(description="List of job IDs to stop")],
            folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
            strategy: Annotated[str, Field(description="SoftStop or Kill")] = "SoftStop",
        ) -> str:
            """
            Stop multiple jobs at once.
            Sends a stop request for each job ID concurrently and reports results.
            """
            st = _state(ctx)

            async def stop_one(jid: int) -> dict[str, Any]:
                try:
                    body = {"jobId": jid, "strategy": strategy}
                    await st.client.post("Jobs", body=body, action="StopJob", folder_id=folder_id)
                    return {"job_id": jid, "status": "stop_requested"}
                except UiPathError as e:
                    return {"job_id": jid, "status": "error", "error": e.message}

            results = list(await asyncio.gather(*[stop_one(jid) for jid in job_ids]))
            success = sum(1 for r in results if r["status"] == "stop_requested")
            return json.dumps(
                {"total": len(job_ids), "success": success, "results": results}, default=str
            )

    # ── wait_for_job ⭐new ────────────────────────────────────────────────────

    @mcp.tool()
    async def wait_for_job(
        ctx: Context,
        job_id: Annotated[int, Field(description="Job ID to wait for")],
        folder_id: Annotated[int | None, Field(description="Folder ID")] = None,
        timeout_seconds: Annotated[
            int, Field(description="Max seconds to wait before giving up", ge=10, le=3600)
        ] = 300,
        poll_interval_seconds: Annotated[
            int, Field(description="Seconds between status polls", ge=5, le=60)
        ] = 10,
    ) -> str:
        """
        Poll a job until it reaches a terminal state (Successful, Faulted, Stopped).
        Reports progress while waiting and returns the final job state + output arguments.
        """
        st = _state(ctx)
        terminal = {JobState.SUCCESSFUL, JobState.FAULTED, JobState.STOPPED, JobState.TERMINATING}
        elapsed = 0

        while elapsed < timeout_seconds:
            try:
                data = await st.client.get_by_id("Jobs", job_id, folder_id=folder_id)
                job = Job.model_validate(data)

                if job.state in terminal:
                    result = job.model_dump()
                    if job.output_arguments:
                        try:
                            result["output_arguments_parsed"] = json.loads(job.output_arguments)
                        except json.JSONDecodeError:
                            pass
                    return json.dumps(
                        {"final_state": job.state, "elapsed_seconds": elapsed, "job": result},
                        default=str,
                    )
            except UiPathError as e:
                return json.dumps(e.to_dict())

            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds

        return json.dumps(
            {
                "error": f"Job {job_id} did not complete within {timeout_seconds}s",
                "elapsed_seconds": elapsed,
            }
        )
