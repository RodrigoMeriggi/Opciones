variable "name" { type = string }
variable "environment" { type = string }
variable "tags" { type = map(string) }

resource "aws_vpc" "this" {
  cidr_block           = "10.20.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = merge(var.tags, { Name = "${var.name}-vpc" })
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = "10.20.1.0/24"
  availability_zone       = "${data.aws_region.current.name}a"
  map_public_ip_on_launch = true
  tags                    = merge(var.tags, { Name = "${var.name}-public-a" })
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.this.id
  cidr_block              = "10.20.2.0/24"
  availability_zone       = "${data.aws_region.current.name}b"
  map_public_ip_on_launch = true
  tags                    = merge(var.tags, { Name = "${var.name}-public-b" })
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.this.id
  cidr_block        = "10.20.11.0/24"
  availability_zone = "${data.aws_region.current.name}a"
  tags              = merge(var.tags, { Name = "${var.name}-private-a" })
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.this.id
  cidr_block        = "10.20.12.0/24"
  availability_zone = "${data.aws_region.current.name}b"
  tags              = merge(var.tags, { Name = "${var.name}-private-b" })
}

data "aws_region" "current" {}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.this.id
  tags   = var.tags
}

output "vpc_id" { value = aws_vpc.this.id }
output "public_subnet_ids" { value = [aws_subnet.public_a.id, aws_subnet.public_b.id] }
output "private_subnet_ids" { value = [aws_subnet.private_a.id, aws_subnet.private_b.id] }
