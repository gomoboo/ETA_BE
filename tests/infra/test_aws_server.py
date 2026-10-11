import subprocess

import pytest

from infra.scripts.aws_server import Server

REPOSITORY = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/eta-test/api"
TAG = "a" * 40


class FakeServer(Server):
    def __init__(self, state="stopped", remote_fails=False):
        super().__init__("ap-northeast-2", "i-0123456789abcdef0")
        self.current_state = state
        self.calls = []
        self.remote_fails = remote_fails

    def state(self):
        return self.current_state

    def aws(self, *args):
        self.calls.append(args)
        return {}

    def remote(self, command):
        self.calls.append(("remote", command))
        if self.remote_fails:
            raise RuntimeError("health check failed")


def test_start_waits_for_running_status_and_api_health():
    server = FakeServer()
    server.start()
    assert [call[:3] for call in server.calls[:3]] == [
        ("ec2", "start-instances", "--instance-ids"),
        ("ec2", "wait", "instance-running"),
        ("ec2", "wait", "instance-status-ok"),
    ]
    assert "eta-backend.service" in server.calls[-1][1]
    assert "/health" in server.calls[-1][1]


def test_start_running_server_does_not_restart_instance():
    server = FakeServer("running")
    server.start()
    assert not any("start-instances" in call or "reboot-instances" in call for call in server.calls)


def test_start_failure_does_not_report_success():
    with pytest.raises(RuntimeError, match="health check"):
        FakeServer(remote_fails=True).start()


def test_stop_uses_stop_not_terminate_and_waits():
    server = FakeServer("running")
    server.stop()
    assert server.calls[0][:2] == ("ec2", "stop-instances")
    assert server.calls[-1][:3] == ("ec2", "wait", "instance-stopped")
    assert not any("terminate-instances" in call for call in server.calls)


def test_stop_is_idempotent():
    server = FakeServer()
    server.stop()
    assert server.calls == []


def test_start_finishes_pending_stop_first():
    server = FakeServer("stopping")
    server.start()
    assert server.calls[0][:3] == ("ec2", "wait", "instance-stopped")
    assert server.calls[1][:2] == ("ec2", "start-instances")


def test_deploy_while_stopped_selects_image_without_starting_server():
    server = FakeServer()
    server.deploy(REPOSITORY, TAG, "/eta-test/desired-image")
    assert server.calls[0][:2] == ("ecr", "describe-images")
    assert server.calls[-1][:2] == ("ssm", "put-parameter")
    assert server.calls[-1][-1] == f"{REPOSITORY}:{TAG}"
    assert not any(call[0] in ("ec2", "remote") for call in server.calls)


def test_deploy_running_server_replaces_api_before_selecting_image():
    server = FakeServer("running")
    server.deploy(REPOSITORY, TAG, "/eta-test/desired-image")
    assert server.calls[1][0] == "remote"
    assert "deploy.sh" in server.calls[1][1]
    assert server.calls[2][:2] == ("ssm", "put-parameter")


def test_failed_replacement_does_not_select_failed_image():
    server = FakeServer("running", remote_fails=True)
    with pytest.raises(RuntimeError):
        server.deploy(REPOSITORY, TAG, "/eta-test/desired-image")
    assert not any("put-parameter" in call for call in server.calls)


@pytest.mark.parametrize("state", ["pending", "stopping", "terminated"])
def test_deploy_rejects_unstable_states(state):
    server = FakeServer(state)
    with pytest.raises(RuntimeError):
        server.deploy(REPOSITORY, TAG, "/eta-test/desired-image")
    assert not any(call[0] == "remote" or "put-parameter" in call for call in server.calls)


@pytest.mark.parametrize("tag", ["latest", "main; reboot", "abc", "A" * 40])
def test_deploy_rejects_untrusted_tags_before_aws_call(tag):
    server = FakeServer()
    with pytest.raises(ValueError):
        server.deploy(REPOSITORY, tag, "/eta-test/desired-image")
    assert server.calls == []


def test_remote_waits_for_ssm_and_checks_command_success(monkeypatch):
    server = Server("ap-northeast-2", "i-0123456789abcdef0")
    responses = iter([
        {"InstanceInformationList": []},
        {"InstanceInformationList": [{"PingStatus": "Online"}]},
        {"Command": {"CommandId": "command-1"}},
        subprocess.CalledProcessError(1, "aws", stderr="InvocationDoesNotExist"),
        {"Status": "InProgress"},
        {"Status": "Success", "StandardOutputContent": "healthy"},
    ])
    def aws(*args):
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(server, "aws", aws)
    monkeypatch.setattr("infra.scripts.aws_server.time.sleep", lambda _: None)
    server.remote("curl localhost/health")


def test_remote_failed_command_is_not_success(monkeypatch):
    server = Server("ap-northeast-2", "i-0123456789abcdef0")
    responses = iter([
        {"InstanceInformationList": [{"PingStatus": "Online"}]},
        {"Command": {"CommandId": "command-1"}},
        {"Status": "Failed", "StandardErrorContent": "service failed"},
    ])
    monkeypatch.setattr(server, "aws", lambda *args: next(responses))
    with pytest.raises(RuntimeError, match="service failed"):
        server.remote("false")
