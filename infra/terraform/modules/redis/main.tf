variable "name" { type = string }
variable "subnet_ids" { type = list(string) }
variable "vpc_security_group_ids" { type = list(string) }
variable "tags" { type = map(string) }

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name}-redis"
  subnet_ids = var.subnet_ids
}

resource "aws_elasticache_cluster" "this" {
  cluster_id           = "${var.name}-redis"
  engine               = "redis"
  node_type            = "cache.t4g.micro"
  num_cache_nodes      = 1
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.this.name
  security_group_ids   = var.vpc_security_group_ids
  tags                 = var.tags
}

output "redis_id" { value = aws_elasticache_cluster.this.id }
