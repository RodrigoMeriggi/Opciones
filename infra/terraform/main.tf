terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["local", "development", "staging", "production"], var.environment)
    error_message = "environment inválido"
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project" {
  type    = string
  default = "opciones"
}

locals {
  name = "${var.project}-${var.environment}"
  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    LiveTrading = "disabled-by-default"
  }
}

provider "aws" {
  region = var.aws_region
}

module "networking" {
  source      = "./modules/networking"
  name        = local.name
  environment = var.environment
  tags        = local.common_tags
}

module "security" {
  source = "./modules/security"
  name   = local.name
  tags   = local.common_tags
}

module "database" {
  source                = "./modules/database"
  name                  = local.name
  environment           = var.environment
  subnet_ids            = module.networking.private_subnet_ids
  vpc_security_group_ids = [module.security.rds_sg_id]
  tags                  = local.common_tags
}

module "redis" {
  source                 = "./modules/redis"
  name                   = local.name
  subnet_ids             = module.networking.private_subnet_ids
  vpc_security_group_ids = [module.security.redis_sg_id]
  tags                   = local.common_tags
}

module "secrets" {
  source      = "./modules/secrets"
  name        = local.name
  environment = var.environment
  tags        = local.common_tags
}

module "logging" {
  source = "./modules/logging"
  name   = local.name
  tags   = local.common_tags
}

module "backend" {
  source             = "./modules/backend"
  name               = local.name
  environment        = var.environment
  private_subnet_ids = module.networking.private_subnet_ids
  api_sg_id          = module.security.api_sg_id
  execution_role_arn = module.security.ecs_execution_role_arn
  task_role_arn      = module.security.api_task_role_arn
  secrets_arn        = module.secrets.app_secret_arn
  log_group          = module.logging.api_log_group
  tags               = local.common_tags
}

module "worker" {
  source             = "./modules/worker"
  name               = local.name
  environment        = var.environment
  private_subnet_ids = module.networking.private_subnet_ids
  worker_sg_id       = module.security.worker_sg_id
  execution_role_arn = module.security.ecs_execution_role_arn
  task_role_arn      = module.security.worker_task_role_arn
  secrets_arn        = module.secrets.app_secret_arn
  log_group          = module.logging.worker_log_group
  desired_count      = 1
  tags               = local.common_tags
}

module "frontend" {
  source            = "./modules/frontend"
  name              = local.name
  public_subnet_ids = module.networking.public_subnet_ids
  frontend_sg_id    = module.security.frontend_sg_id
  execution_role_arn = module.security.ecs_execution_role_arn
  task_role_arn     = module.security.frontend_task_role_arn
  log_group         = module.logging.frontend_log_group
  tags              = local.common_tags
}

module "backups" {
  source      = "./modules/backups"
  name        = local.name
  environment = var.environment
  db_arn      = module.database.db_arn
  tags        = local.common_tags
}

module "monitoring" {
  source      = "./modules/monitoring"
  name        = local.name
  environment = var.environment
  tags        = local.common_tags
}

output "notes" {
  value = "LIVE_TRADING_ENABLED must remain false after deploy. Worker desiredCount=1."
}
