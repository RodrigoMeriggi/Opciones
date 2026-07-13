variable "name" { type = string }
variable "environment" { type = string }
variable "db_arn" { type = string }
variable "tags" { type = map(string) }

output "rpo_hours" { value = var.environment == "production" ? 1 : 24 }
output "rto_hours" { value = var.environment == "production" ? 4 : 24 }
output "note" {
  value = "After restore: block entries, reconcile broker, require manual validation"
}
