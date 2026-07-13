variable "name" { type = string }
variable "tags" { type = map(string) }

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.name}/api"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "worker" {
  name              = "/ecs/${var.name}/worker"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${var.name}/frontend"
  retention_in_days = 14
  tags              = var.tags
}

output "api_log_group" { value = aws_cloudwatch_log_group.api.name }
output "worker_log_group" { value = aws_cloudwatch_log_group.worker.name }
output "frontend_log_group" { value = aws_cloudwatch_log_group.frontend.name }
