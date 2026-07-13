variable "name" { type = string }
variable "environment" { type = string }
variable "tags" { type = map(string) }

resource "aws_secretsmanager_secret" "app" {
  name = "${var.name}/app"
  tags = var.tags
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    TRADING_MODE            = "paper"
    LIVE_TRADING_ENABLED    = "false"
    EMERGENCY_STOP          = "true"
    DASHBOARD_JWT_SECRET    = "rotate-me"
    # BROKER_* intentionally empty until docs + dual approval
  })
}

output "app_secret_arn" { value = aws_secretsmanager_secret.app.arn }
