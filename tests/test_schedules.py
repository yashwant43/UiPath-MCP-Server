from __future__ import annotations

import json
from unittest.mock import AsyncMock

from uipath_mcp.tools.schedules import register

from .conftest import make_mock_ctx


class ToolRegistry:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self):
        def decorator(function):
            self.tools[function.__name__] = function
            return function

        return decorator


async def test_list_schedules_returns_every_trigger_type_and_machine_target(
    pat_settings,
) -> None:
    client = AsyncMock()
    client.get.side_effect = [
        {
            "@odata.count": 2,
            "value": [
                {
                    "Id": 178169,
                    "Name": "HourlyTrigger",
                    "ReleaseName": "AiriaExpenseDocument",
                    "Enabled": True,
                    "StartProcessCron": "0 0/30 * * * ?",
                    "MachineRobots": [
                        {
                            "MachineId": 255744,
                            "MachineName": "UnattendedTemplate_QVWPUIPR4",
                            "RobotId": None,
                            "RobotUserName": None,
                            "HostMachineName": "QVWPUIPR4",
                        }
                    ],
                },
                {
                    "Id": 200,
                    "Name": "QueueTrigger",
                    "ReleaseName": "QueueWorker",
                    "Enabled": False,
                    "QueueDefinitionId": 99,
                    "MachineRobots": [],
                },
            ],
        },
        {
            "@odata.count": 1,
            "value": [
                {
                    "Id": 300,
                    "Name": "ConnectedEvent",
                    "ProcessName": "EventWorker",
                    "Enabled": True,
                    "MachineRobots": [],
                }
            ],
        },
        {
            "@odata.count": 1,
            "value": [
                {
                    "Id": 400,
                    "Name": "InboundApi",
                    "ProcessName": "ApiWorker",
                    "Enabled": True,
                    "MachineRobots": [],
                }
            ],
        },
    ]
    registry = ToolRegistry()
    register(registry, read_only=True)
    ctx = make_mock_ctx(client, pat_settings)

    result = json.loads(
        await registry.tools["list_schedules"](ctx, folder_id=1456232, enabled_only=False, top=50)
    )

    assert [call.args[0] for call in client.get.await_args_list] == [
        "ProcessSchedules",
        "ApiTriggers",
        "HttpTriggers",
    ]
    assert result["total_count"] == 4
    assert {trigger["trigger_type"] for trigger in result["schedules"]} == {
        "time",
        "queue",
        "event",
        "api",
    }
    airia = next(trigger for trigger in result["schedules"] if trigger["id"] == 178169)
    assert airia["machine_robots"][0] == {
        "machine_id": 255744,
        "machine_name": "UnattendedTemplate_QVWPUIPR4",
        "robot_id": None,
        "robot_username": None,
        "host_machine_name": "QVWPUIPR4",
    }


async def test_list_schedules_applies_enabled_filter_to_every_trigger_endpoint(
    pat_settings,
) -> None:
    client = AsyncMock()
    client.get.side_effect = [
        {"value": []},
        {"value": []},
        {"value": []},
    ]
    registry = ToolRegistry()
    register(registry, read_only=True)
    ctx = make_mock_ctx(client, pat_settings)

    await registry.tools["list_schedules"](ctx, folder_id=1, enabled_only=True, top=10)

    for call in client.get.await_args_list:
        assert call.kwargs["params"]["$filter"] == "Enabled eq true"
        assert call.kwargs["folder_id"] == 1
