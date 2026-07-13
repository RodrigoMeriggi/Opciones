variable "name" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "frontend_sg_id" { type = string }
variable "execution_role_arn" { type = string }
variable "task_role_arn" { type = string }
variable "log_group" { type = string }
variable "tags" { type = map(string) }

output "service_name" { value = "${var.name}-frontend" }
