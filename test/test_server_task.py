"""Test client/server stop/start."""
import asyncio
import logging
import os
import subprocess
from time import sleep

import pytest
import pytest_asyncio

from pymodbus import client, pymodbus_apply_logging_config, server
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.transaction import (
    ModbusRtuFramer,
    ModbusSocketFramer,
    ModbusTlsFramer,
)


_logger = logging.getLogger()
pymodbus_apply_logging_config()
_logger.setLevel(logging.DEBUG)

TEST_RUN_COUNT = 1
TEST_TYPES = ["tcp", "udp", "serial", "tls"]


@pytest_asyncio.fixture(name="configs", params=TEST_TYPES)
def setup_fixture(request, def_type):
    """Run as fixture."""
    return setup_client_server(request, def_type)


@pytest.fixture(name="_run_sync_server")
def fixture_sync_server(configs):
    """Start sync server"""
    _run_server, _run_client, _server_args, _client_args, comm = configs
    cwd = os.getcwd().split("/")[-1]
    if cwd == "test":
        path = "../examples"
    elif pytest.IS_WINDOWS:
        path = "examples"
    else:
        path = "./examples"
    proc = subprocess.Popen(
        [f"{path}/server_sync.py", "--log",  "debug",  "--comm",  comm],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        # shell=True
    )  # nosec
    sleep(0.1)
    yield
    proc.terminate()
    while proc.poll() is None:
        proc.kill()
        sleep(0.1)


def setup_client_server(request, def_type):
    """Do setup of single test-"""
    pymodbus_apply_logging_config()
    _logger.setLevel("DEBUG")
    datablock = ModbusSequentialDataBlock(0x00, [17] * 100)
    context = ModbusServerContext(
        slaves=ModbusSlaveContext(
            di=datablock, co=datablock, hr=datablock, ir=datablock, unit=1
        ),
        single=True,
    )
    cwd = os.getcwd().split("/")[-1]
    path = "../examples" if cwd == "test" else "examples"
    cfg = {
        "serial": {
            "srv_args": {
                "context": context,
                "framer": ModbusRtuFramer,
                "port": "socket://127.0.0.1:5020",
            },
            "cli_args": {
                "framer": ModbusRtuFramer,
                "port": "socket://127.0.0.1:5020",
            },
            "async": {
                "srv": server.StartAsyncSerialServer,
                "cli": client.AsyncModbusSerialClient,
            },
            "sync": {
                "srv": server.StartSerialServer,
                "cli": client.ModbusSerialClient,
            },
        },
        "tcp": {
            "srv_args": {
                "context": context,
                "framer": ModbusSocketFramer,
                "address": ("127.0.0.1", 5020),
                "allow_reuse_address": True,
            },
            "cli_args": {
                "framer": ModbusSocketFramer,
                "host": "127.0.0.1",
                "port": 5020,
            },
            "async": {
                "srv": server.StartAsyncTcpServer,
                "cli": client.AsyncModbusTcpClient,
            },
            "sync": {
                "srv": server.StartTcpServer,
                "cli": client.ModbusTcpClient,
            },
        },
        "tls": {
            "srv_args": {
                "context": context,
                "framer": ModbusTlsFramer,
                "address": ("127.0.0.1", 5020),
                "allow_reuse_address": True,
                "certfile": f"{path}/certificates/pymodbus.crt",
                "keyfile": f"{path}/certificates/pymodbus.key",
            },
            "cli_args": {
                "framer": ModbusTlsFramer,
                "host": "127.0.0.1",
                "port": 5020,
                "certfile": f"{path}/certificates/pymodbus.crt",
                "keyfile": f"{path}/certificates/pymodbus.key",
                "server_hostname": "localhost",
            },
            "async": {
                "srv": server.StartAsyncTlsServer,
                "cli": client.AsyncModbusTlsClient,
            },
            "sync": {
                "srv": server.StartTlsServer,
                "cli": client.ModbusTlsClient,
            },
        },
        "udp": {
            "srv_args": {
                "context": context,
                "framer": ModbusSocketFramer,
                "address": ("127.0.0.1", 5020),
            },
            "cli_args": {
                "framer": ModbusSocketFramer,
                "host": "127.0.0.1",
                "port": 5020,
            },
            "async": {
                "srv": server.StartAsyncUdpServer,
                "cli": client.AsyncModbusUdpClient,
            },
            "sync": {
                "srv": server.StartUdpServer,
                "cli": client.ModbusUdpClient,
            },
        },
    }

    if isinstance(request, str):
        comm = request
    else:
        comm = request.param
    cur = cfg[comm]
    cur_m = cur[def_type]
    return cur_m["srv"], cur_m["cli"], cur["srv_args"], cur["cli_args"], comm


@pytest.mark.parametrize("def_type", ["async"])
@pytest.mark.parametrize("_count", range(TEST_RUN_COUNT))
async def test_async_task_listen(configs, _count):
    """Test stop when not connected."""
    run_server, _run_client, server_args, _client_args, _comm = configs
    task = asyncio.create_task(run_server(**server_args))
    await asyncio.sleep(0.1)
    await server.ServerAsyncStop()
    await task


@pytest.mark.parametrize("def_type", ["async"])
@pytest.mark.parametrize("_count", range(TEST_RUN_COUNT))
async def test_async_task_connected(configs, _count):
    """Test stop when connected."""
    run_server, run_client, server_args, client_args, _comm = configs
    asyncio.create_task(run_server(**server_args))
    await asyncio.sleep(0.1)
    test_client = run_client(**client_args)
    await test_client.connect()
    await asyncio.sleep(0.1)
    assert test_client.protocol

    rr = await test_client.read_coils(1, 1, slave=0x01)
    assert len(rr.bits) == 8

    await test_client.close()
    await asyncio.sleep(0.1)
    await server.ServerAsyncStop()
    await asyncio.sleep(1)


@pytest.mark.parametrize("def_type", ["async"])
@pytest.mark.parametrize("_count", range(TEST_RUN_COUNT))
async def test_async_task_after_connect(configs, _count):
    """Test stop when connected."""
    run_server, run_client, server_args, client_args, _comm = configs
    asyncio.create_task(run_server(**server_args))
    await asyncio.sleep(0.1)
    test_client = run_client(**client_args)
    await test_client.connect()
    await asyncio.sleep(0.1)
    assert test_client.protocol

    await server.ServerAsyncStop()
    await asyncio.sleep(0.1)
    await test_client.close()
    await asyncio.sleep(0.1)


@pytest.mark.parametrize("def_type", ["sync"])
@pytest.mark.parametrize("_count", range(TEST_RUN_COUNT))
def test_task_listen(_run_sync_server, _count):
    """Test stop when not connected."""


@pytest.mark.parametrize("def_type", ["sync"])
@pytest.mark.parametrize("_count", range(TEST_RUN_COUNT))
def test_task_connected(configs, _run_sync_server, _count):
    """Test stop when connected."""
    _run_server, run_client, _server_args, client_args, comm = configs
    # JAN WAITING
    if comm in {"udp", "tls", "serial"}:
        return
    sleep(1)

    test_client = run_client(**client_args)
    test_client.connect()
    assert test_client.connected

    rr = test_client.read_coils(1, 1, slave=1)
    assert len(rr.bits) == 8

    test_client.close()


@pytest.mark.parametrize("def_type", ["sync"])
@pytest.mark.parametrize("_count", range(TEST_RUN_COUNT))
def test_task_after_connect(configs, _run_sync_server, _count):
    """Test stop when connected."""
    _run_server, run_client, _server_args, client_args, comm = configs
    if comm in {"udp", "tls", "serial"}:
        return
    sleep(1)

    test_client = run_client(**client_args)
    test_client.connect()
    assert test_client.connected
