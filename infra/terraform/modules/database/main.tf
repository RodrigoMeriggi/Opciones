variable "name" { type = string }
variable "environment" { type = string }
variable "subnet_ids" { type = list(string) }
variable "vpc_security_group_ids" { type = list(string) }
variable "tags" { type = map(string) }

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-db"
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_db_instance" "this" {
  identifier     = "${var.name}-postgres"
  engine         = "postgres"
  engine_version = "16"
  instance_class = var.environment == "production" ? "db.t4g.medium" : "db.t4g.micro"
  allocated_storage = 20
  storage_encrypted = true
  multi_az          = var.environment == "production"
  db_subnet_group_name = aws_db_subnet_group.this.name
  vpc_security_group_ids = var.vpc_security_group_ids
  username = "opciones"
  manage_master_user_password = true
  skip_final_snapshot = var.environment != "production"
  deletion_protection = var.environment == "production"
  backup_retention_period = var.environment == "production" ? 14 : 3
  publicly_accessible = false
  tags = var.tags
}

output "db_arn" { value = aws_db_instance.this.arn }
output "db_endpoint" { value = aws_db_instance.this.address }
