# Esqueleto ECS API — imagen sin secretos; health check; non-root en Dockerfile
variable "name" { type = string }
variable "environment" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "api_sg_id" { type = string }
variable "execution_role_arn" { type = string }
variable "task_role_arn" { type = string }
variable "secrets_arn" { type = string }
variable "log_group" { type = string }
variable "tags" { type = map(string) }

output "service_name" { value = "${var.name}-api" }
output "note" { value = "Definir aws_ecs_service en despliegue real con imagen ECR fija" }
