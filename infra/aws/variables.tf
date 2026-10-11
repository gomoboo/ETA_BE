variable "aws_region" {
  type    = string
  default = "ap-northeast-2"
}
variable "project_name" {
  type    = string
  default = "eta-test"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,30}$", var.project_name))
    error_message = "Use a lowercase project name of 2-31 characters."
  }
}
variable "instance_type" {
  type    = string
  default = "t3.medium"
  validation {
    condition     = can(regex("^t3a?\\.(micro|small|medium|large)$", var.instance_type))
    error_message = "The Ubuntu bootstrap uses an x86_64 T3/T3a instance."
  }
}
variable "disk_size_gb" {
  type    = number
  default = 30
  validation {
    condition     = var.disk_size_gb >= 30
    error_message = "Allocate at least 30 GiB for Docker images and persistent database data."
  }
}
variable "repository" {
  type    = string
  default = "gomoboo/ETA_BE"
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", var.repository))
    error_message = "Use owner/repository. The bootstrap supports public repositories."
  }
}
variable "code_ref" {
  description = "Initial public Git checkout; subsequent versions are deployed as ECR images."
  type        = string
  default     = "main"
  validation {
    condition     = can(regex("^[A-Za-z0-9_./-]+$", var.code_ref)) && !startswith(var.code_ref, "-")
    error_message = "Use a branch, tag or commit SHA."
  }
}
variable "api_domain" {
  description = "DNS name pointed at the output public IP; Caddy issues HTTPS automatically."
  type        = string
  default     = ""
  validation {
    condition     = var.api_domain == "" || can(regex("^[A-Za-z0-9][A-Za-z0-9.-]+\\.[A-Za-z]{2,}$", var.api_domain))
    error_message = "Use a DNS name without a scheme, path or port."
  }
}
variable "allowed_web_cidrs" {
  description = "80/443 ingress. Without a domain, restrict this to the testers' public IPs."
  type        = set(string)
  default     = ["0.0.0.0/0"]
  validation {
    condition     = alltrue([for cidr in var.allowed_web_cidrs : can(cidrnetmask(cidr))])
    error_message = "Use IPv4 CIDRs."
  }
}
variable "allow_plain_http" {
  description = "Explicit opt-in for temporary IP-only testing; requires restricted IPv4 ingress."
  type        = bool
  default     = false
}
variable "github_oidc_subject" {
  description = "Exact main-branch OIDC subject. Default uses this repository's immutable IDs."
  type        = string
  default     = "repo:gomoboo@328260111/ETA_BE@1397206353:ref:refs/heads/main"
  validation {
    condition     = startswith(var.github_oidc_subject, "repo:") && endswith(var.github_oidc_subject, ":ref:refs/heads/main") && !strcontains(var.github_oidc_subject, "*")
    error_message = "Trust an exact repository's main branch, without wildcards."
  }
}
variable "existing_github_oidc_provider_arn" {
  description = "If GitHub OIDC already exists in the AWS account, supply its ARN instead of creating another."
  type        = string
  default     = ""
}
