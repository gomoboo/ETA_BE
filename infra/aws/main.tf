data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_availability_zones" "available" {
  state = "available"
}
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}
locals {
  prefix       = "arn:${data.aws_partition.current.partition}"
  account      = data.aws_caller_identity.current.account_id
  env_path     = "/${var.project_name}/backend-env"
  image_path   = "/${var.project_name}/desired-image"
  env_arn      = "${local.prefix}:ssm:${var.aws_region}:${local.account}:parameter${local.env_path}"
  image_arn    = "${local.prefix}:ssm:${var.aws_region}:${local.account}:parameter${local.image_path}"
  oidc_arn     = var.existing_github_oidc_provider_arn != "" ? var.existing_github_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
  instance_arn = "${local.prefix}:ec2:${var.aws_region}:${local.account}:instance/${aws_instance.server.id}"
  bootstrap_config = {
    region          = var.aws_region, project = var.project_name, repository = var.repository,
    ref             = var.code_ref, domain = var.api_domain, env_parameter = local.env_path,
    image_parameter = local.image_path, ecr_registry = split("/", aws_ecr_repository.api.repository_url)[0]
  }
}
resource "aws_vpc" "server" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = var.project_name }
}
resource "aws_internet_gateway" "server" {
  vpc_id = aws_vpc.server.id
}
resource "aws_subnet" "server" {
  vpc_id                  = aws_vpc.server.id
  cidr_block              = "10.42.1.0/24"
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true
}
resource "aws_route_table" "server" {
  vpc_id = aws_vpc.server.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.server.id
  }
}
resource "aws_route_table_association" "server" {
  subnet_id      = aws_subnet.server.id
  route_table_id = aws_route_table.server.id
}
resource "aws_security_group" "server" {
  name_prefix = "${var.project_name}-"
  description = "Web ingress only; administration uses SSM instead of SSH."
  vpc_id      = aws_vpc.server.id
}
resource "aws_vpc_security_group_ingress_rule" "http" {
  for_each          = var.allowed_web_cidrs
  security_group_id = aws_security_group.server.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}
resource "aws_vpc_security_group_ingress_rule" "https" {
  for_each          = var.api_domain == "" ? toset([]) : var.allowed_web_cidrs
  security_group_id = aws_security_group.server.id
  cidr_ipv4         = each.value
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
resource "aws_vpc_security_group_egress_rule" "outbound" {
  security_group_id = aws_security_group.server.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}
resource "aws_ecr_repository" "api" {
  name                 = "${var.project_name}/api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
}
resource "aws_ssm_parameter" "desired_image" {
  name  = local.image_path
  type  = "String"
  value = "bootstrap"
  lifecycle { ignore_changes = [value] } # CD owns subsequent image selections; contains no secret.
}
resource "aws_iam_role" "server" {
  name = "${var.project_name}-server"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}
resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.server.name
  policy_arn = "${local.prefix}:iam::aws:policy/AmazonSSMManagedInstanceCore"
}
resource "aws_iam_role_policy" "server" {
  role = aws_iam_role.server.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [
      { Effect = "Allow", Action = ["ssm:GetParameter"], Resource = [local.env_arn, local.image_arn] },
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"], Resource = aws_ecr_repository.api.arn }
    ]
  })
}
resource "aws_iam_instance_profile" "server" {
  name = "${var.project_name}-server"
  role = aws_iam_role.server.name
}
resource "aws_instance" "server" {
  ami                         = data.aws_ami.ubuntu.id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.server.id
  vpc_security_group_ids      = [aws_security_group.server.id]
  iam_instance_profile        = aws_iam_instance_profile.server.name
  disable_api_termination     = true
  user_data_replace_on_change = false
  user_data = templatefile("${path.module}/user-data.sh.tftpl", {
    config     = base64encode(jsonencode(local.bootstrap_config)),
    repository = var.repository, code_ref = var.code_ref
  })
  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  credit_specification { cpu_credits = "standard" } # No automatic surplus-credit charges.
  root_block_device {
    volume_size           = var.disk_size_gb
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = false
    tags                  = { Name = "${var.project_name}-persistent-data" }
  }
  tags = { Name = var.project_name }
  lifecycle {
    prevent_destroy = true
    ignore_changes  = [ami, user_data]
    precondition {
      condition = var.api_domain != "" || (
        var.allow_plain_http && length(var.allowed_web_cidrs) > 0 &&
        alltrue([for cidr in var.allowed_web_cidrs : tonumber(split("/", cidr)[1]) >= 24])
      )
      error_message = "Set api_domain for HTTPS, or explicitly enable temporary HTTP with /24 or narrower tester CIDRs."
    }
  }
  depends_on = [aws_route_table_association.server, aws_iam_role_policy.server, aws_iam_role_policy_attachment.ssm]
}
resource "aws_eip" "server" {
  domain = "vpc"
}
resource "aws_eip_association" "server" {
  instance_id   = aws_instance.server.id
  allocation_id = aws_eip.server.id
}
resource "aws_iam_openid_connect_provider" "github" {
  count          = var.existing_github_oidc_provider_arn == "" ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}
resource "aws_iam_role" "actions" {
  name = "${var.project_name}-github-actions"
  assume_role_policy = jsonencode({
    Version = "2012-10-17", Statement = [{
      Effect = "Allow", Action = "sts:AssumeRoleWithWebIdentity", Principal = { Federated = local.oidc_arn },
      Condition = { StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com",
        "token.actions.githubusercontent.com:sub" = var.github_oidc_subject
      } }
    }]
  })
}
resource "aws_iam_role_policy" "actions" {
  role = aws_iam_role.actions.id
  policy = jsonencode({
    Version = "2012-10-17", Statement = [
      { Effect = "Allow", Action = ["ec2:StartInstances", "ec2:StopInstances"], Resource = local.instance_arn },
      { Effect = "Allow", Action = ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus", "ssm:DescribeInstanceInformation", "ssm:GetCommandInvocation"], Resource = "*" },
      { Effect = "Allow", Action = ["ssm:SendCommand"], Resource = [local.instance_arn, "${local.prefix}:ssm:${var.aws_region}::document/AWS-RunShellScript"] },
      { Effect = "Allow", Action = ["ssm:PutParameter"], Resource = local.image_arn },
      { Effect = "Allow", Action = ["ecr:GetAuthorizationToken"], Resource = "*" },
      { Effect = "Allow", Action = ["ecr:DescribeImages", "ecr:BatchGetImage", "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage"], Resource = aws_ecr_repository.api.arn }
    ]
  })
}
