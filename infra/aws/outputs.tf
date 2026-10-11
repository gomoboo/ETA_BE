output "instance_id" { value = aws_instance.server.id }
output "public_ip" { value = aws_eip.server.public_ip }
output "aws_region" { value = var.aws_region }
output "actions_role_arn" { value = aws_iam_role.actions.arn }
output "ecr_repository" { value = aws_ecr_repository.api.repository_url }
output "environment_parameter" { value = local.env_path }
output "desired_image_parameter" { value = local.image_path }
output "api_url" { value = var.api_domain == "" ? "http://${aws_eip.server.public_ip}" : "https://${var.api_domain}" }
output "github_variables" {
  value = {
    AWS_REGION      = var.aws_region, AWS_ROLE_ARN = aws_iam_role.actions.arn,
    AWS_INSTANCE_ID = aws_instance.server.id, ECR_REPOSITORY = aws_ecr_repository.api.repository_url,
    IMAGE_PARAMETER = local.image_path
  }
}
