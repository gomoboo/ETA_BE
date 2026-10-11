mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_partition" { defaults = { partition = "aws" } }
  mock_data "aws_availability_zones" { defaults = { names = ["ap-northeast-2a"] } }
  mock_data "aws_ami" { defaults = { id = "ami-0123456789abcdef0" } }
  mock_resource "aws_ecr_repository" {
    defaults = {
      arn            = "arn:aws:ecr:ap-northeast-2:123456789012:repository/eta-test/api"
      repository_url = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/eta-test/api"
    }
  }
  mock_resource "aws_instance" { defaults = { id = "i-0123456789abcdef0" } }
}
variables { api_domain = "api.example.org" }
run "persistent_server" {
  command = apply # Mock provider only: no credentials or AWS requests.
  assert {
    condition     = aws_instance.server.root_block_device[0].encrypted && !aws_instance.server.root_block_device[0].delete_on_termination && aws_instance.server.disable_api_termination
    error_message = "The data disk must be encrypted and retained; accidental termination must be disabled."
  }
  assert {
    condition     = aws_instance.server.metadata_options[0].http_tokens == "required" && aws_instance.server.credit_specification[0].cpu_credits == "standard"
    error_message = "Require IMDSv2 and avoid automatic CPU surplus-credit billing."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.http["0.0.0.0/0"].from_port == 80 && aws_vpc_security_group_ingress_rule.https["0.0.0.0/0"].from_port == 443 && length(aws_security_group.server.ingress) == 0
    error_message = "Only web rules should be provisioned; do not expose SSH, API, PostgreSQL or Redis ports."
  }
  assert {
    condition     = aws_eip_association.server.instance_id == aws_instance.server.id
    error_message = "The stable public address must remain associated with the same EC2 instance."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.actions.policy).Statement[0].Resource == local.instance_arn && jsondecode(aws_iam_role_policy.actions.policy).Statement[0].Action == ["ec2:StartInstances", "ec2:StopInstances"]
    error_message = "Power control must be scoped to this instance and must not allow termination."
  }
  assert {
    condition     = jsondecode(aws_iam_role.actions.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == var.github_oidc_subject
    error_message = "OIDC must match the exact repository/main subject."
  }
  assert {
    condition     = aws_ssm_parameter.desired_image.type == "String" && !strcontains(aws_iam_role_policy.actions.policy, local.env_arn)
    error_message = "Actions may select a non-secret image but must not read the application's secret env."
  }
}
run "plain_http_requires_opt_in" {
  command = plan
  variables { api_domain = "" }
  expect_failures = [aws_instance.server]
}
run "plain_http_cannot_be_public" {
  command = plan
  variables {
    api_domain        = ""
    allow_plain_http  = true
    allowed_web_cidrs = ["0.0.0.0/0"]
  }
  expect_failures = [aws_instance.server]
}
run "restricted_temporary_http" {
  command = plan
  variables {
    api_domain        = ""
    allow_plain_http  = true
    allowed_web_cidrs = ["203.0.113.10/32"]
  }
  assert {
    condition     = length(aws_vpc_security_group_ingress_rule.https) == 0 && length(aws_vpc_security_group_ingress_rule.http) == 1
    error_message = "Temporary HTTP must only open the tester's CIDR."
  }
}
run "reuse_oidc_provider" {
  command = plan
  variables { existing_github_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0
    error_message = "Do not create a duplicate account-wide OIDC provider."
  }
}
