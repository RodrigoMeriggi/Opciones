variable "name" { type = string }
variable "environment" { type = string }
variable "tags" { type = map(string) }

resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name}-api-5xx"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "HTTPCode_Target_5XX_Count"
  namespace           = "AWS/ApplicationELB"
  period              = 60
  statistic           = "Sum"
  threshold           = 5
  alarm_description   = "API 5xx elevated"
  tags                = var.tags
  treat_missing_data  = "notBreaching"
}

output "alarm_name" { value = aws_cloudwatch_metric_alarm.api_5xx.alarm_name }
