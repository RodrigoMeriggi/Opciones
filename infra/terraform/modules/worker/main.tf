variable "name" { type = string }
variable "environment" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "worker_sg_id" { type = string }
variable "execution_role_arn" { type = string }
variable "task_role_arn" { type = string }
variable "secrets_arn" { type = string }
variable "log_group" { type = string }
variable "desired_count" {
  type    = number
  default = 1
}
variable "tags" { type = map(string) }

output "desired_count" { value = var.desired_count }
output "note" {
  value = "CRITICAL: desired_count must remain 1 + Redis distributed lock to avoid duplicate orders"
}
