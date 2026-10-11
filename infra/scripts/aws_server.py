#!/usr/bin/env python3
"""GitHub-hosted runner control; no AWS SDK or Terraform state is needed."""
import argparse
import json
import os
import re
import shlex
import subprocess
import time


class Server:
    def __init__(self, region, instance_id):
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d", region):
            raise ValueError("Set AWS_REGION to an AWS region")
        if not re.fullmatch(r"i-(?:[0-9a-f]{8}|[0-9a-f]{17})", instance_id):
            raise ValueError("Set AWS_INSTANCE_ID to the Terraform instance_id output")
        self.region = region
        self.instance_id = instance_id

    def aws(self, *args):
        result = subprocess.run(
            ["aws", "--region", self.region, "--output", "json", *args],
            check=True, capture_output=True, text=True,
        )
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def state(self):
        response = self.aws("ec2", "describe-instances", "--instance-ids", self.instance_id)
        return response["Reservations"][0]["Instances"][0]["State"]["Name"]

    def wait(self, waiter):
        self.aws("ec2", "wait", waiter, "--instance-ids", self.instance_id)

    def remote(self, command):
        for _ in range(60):
            result = self.aws("ssm", "describe-instance-information", "--filters", json.dumps([
                {"Key": "InstanceIds", "Values": [self.instance_id]}
            ]))
            if any(i["PingStatus"] == "Online" for i in result["InstanceInformationList"]):
                break
            time.sleep(5)
        else:
            raise TimeoutError("SSM is not online; inspect EC2 cloud-init and its IAM role")
        result = self.aws(
            "ssm", "send-command", "--instance-ids", self.instance_id,
            "--document-name", "AWS-RunShellScript", "--parameters",
            json.dumps({"commands": [command], "executionTimeout": ["900"]}),
        )
        command_id = result["Command"]["CommandId"]
        for _ in range(300):
            try:
                invocation = self.aws("ssm", "get-command-invocation", "--command-id", command_id,
                                      "--instance-id", self.instance_id)
            except subprocess.CalledProcessError as exc:
                if "InvocationDoesNotExist" not in exc.stderr:
                    raise
                time.sleep(3)
                continue
            status = invocation["Status"]
            if status == "Success":
                print(invocation.get("StandardOutputContent", ""))
                return
            if status not in ("Pending", "InProgress", "Delayed"):
                raise RuntimeError(f"SSM command {command_id}: {status}; {invocation.get('StandardErrorContent', '')}")
            time.sleep(3)
        raise TimeoutError(f"SSM command {command_id} exceeded its deadline")

    def start(self):
        state = self.state()
        if state == "stopping":
            self.wait("instance-stopped")
            state = "stopped"
        if state == "stopped":
            self.aws("ec2", "start-instances", "--instance-ids", self.instance_id)
        elif state not in ("running", "pending"):
            raise RuntimeError(f"Cannot start an instance in state {state}")
        self.wait("instance-running")
        self.wait("instance-status-ok")
        self.remote(
            "timeout 300 bash -c 'until systemctl cat eta-backend.service >/dev/null 2>&1; do sleep 5; done' "
            "&& systemctl start eta-backend.service "
            "&& curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/health"
        )
        print("Server is running; API health passed")

    def stop(self):
        state = self.state()
        if state == "stopped":
            print("Server is already stopped")
            return
        if state == "pending":
            self.wait("instance-running")
            state = "running"
        if state == "running":
            self.aws("ec2", "stop-instances", "--instance-ids", self.instance_id)
        elif state != "stopping":
            raise RuntimeError(f"Cannot stop an instance in state {state}")
        self.wait("instance-stopped")
        print("Server stopped; EBS and Elastic IP remain allocated")

    def deploy(self, repository, image_tag, parameter):
        if not re.fullmatch(r"[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9_./-]+", repository):
            raise ValueError("Set ECR_REPOSITORY to the Terraform ECR output")
        if not re.fullmatch(r"[0-9a-f]{40}", image_tag):
            raise ValueError("Use a full 40-character commit SHA image tag")
        if not re.fullmatch(r"/[a-z0-9-]+/desired-image", parameter):
            raise ValueError("Set IMAGE_PARAMETER to the Terraform desired_image_parameter output")
        self.aws("ecr", "describe-images", "--repository-name", repository.split("/", 1)[1],
                 "--image-ids", f"imageTag={image_tag}")
        image = f"{repository}:{image_tag}"
        state = self.state()
        if state == "running":
            self.remote(f"bash /opt/eta/repo/infra/scripts/deploy.sh {shlex.quote(image)}")
        elif state != "stopped":
            raise RuntimeError(f"Wait for server power transition to finish: {state}")
        self.aws("ssm", "put-parameter", "--name", parameter, "--type", "String", "--overwrite", "--value", image)
        print("Image deployed" if state == "running" else "Image selected; server stays stopped and applies it on next boot")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("start", "stop", "status", "deploy"))
    parser.add_argument("--image-tag")
    args = parser.parse_args()
    server = Server(os.environ.get("AWS_REGION", ""), os.environ.get("AWS_INSTANCE_ID", ""))
    if args.action == "deploy":
        server.deploy(os.environ.get("ECR_REPOSITORY", ""), args.image_tag or "", os.environ.get("IMAGE_PARAMETER", ""))
    elif args.action == "status":
        print(server.state())
    else:
        getattr(server, args.action)()


if __name__ == "__main__":
    main()
