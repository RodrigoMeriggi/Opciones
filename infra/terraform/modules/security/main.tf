variable "name" { type = string }
variable "tags" { type = map(string) }

# SGs e IAM de menor privilegio (esqueleto)

resource "aws_security_group" "api" {
  name = "${var.name}-api"
  tags = var.tags
  # vpc_id se inyecta en integración completa
  lifecycle { ignore_changes = [vpc_id] }
}

resource "aws_security_group" "worker" {
  name = "${var.name}-worker"
  tags = var.tags
  lifecycle { ignore_changes = [vpc_id] }
}

resource "aws_security_group" "frontend" {
  name = "${var.name}-frontend"
  tags = var.tags
  lifecycle { ignore_changes = [vpc_id] }
}

resource "aws_security_group" "rds" {
  name = "${var.name}-rds"
  tags = var.tags
  lifecycle { ignore_changes = [vpc_id] }
}

resource "aws_security_group" "redis" {
  name = "${var.name}-redis"
  tags = var.tags
  lifecycle { ignore_changes = [vpc_id] }
}

resource "aws_iam_role" "ecs_execution" {
  name = "${var.name}-ecs-execution"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
    }]
  })
  tags = var.tags
}

resource "aws_iam_role" "api_task" {
  name = "${var.name}-api-task"
  assume_role_policy = aws_iam_role.ecs_execution.assume_role_policy
  tags               = var.tags
}

resource "aws_iam_role" "worker_task" {
  name = "${var.name}-worker-task"
  assume_role_policy = aws_iam_role.ecs_execution.assume_role_policy
  tags               = var.tags
}

resource "aws_iam_role" "frontend_task" {
  name = "${var.name}-frontend-task"
  assume_role_policy = aws_iam_role.ecs_execution.assume_role_policy
  tags               = var.tags
}

output "api_sg_id" { value = aws_security_group.api.id }
output "worker_sg_id" { value = aws_security_group.worker.id }
output "frontend_sg_id" { value = aws_security_group.frontend.id }
output "rds_sg_id" { value = aws_security_group.rds.id }
output "redis_sg_id" { value = aws_security_group.redis.id }
output "ecs_execution_role_arn" { value = aws_iam_role.ecs_execution.arn }
output "api_task_role_arn" { value = aws_iam_role.api_task.arn }
output "worker_task_role_arn" { value = aws_iam_role.worker_task.arn }
output "frontend_task_role_arn" { value = aws_iam_role.frontend_task.arn }
