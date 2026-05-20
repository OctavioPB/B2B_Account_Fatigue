variable "environment"       { type = string }
variable "vpc_id"            { type = string }
variable "subnet_ids"        { type = list(string) }
variable "instance_class"    { type = string }
variable "allocated_storage" { type = number }
variable "db_name"           { type = string }
variable "db_username"       { type = string; sensitive = true }

resource "random_password" "postgres" {
  length           = 32
  special          = true
  override_special = "!#$%^&*()-_=+[]{}|;:,.<>?"
}

resource "aws_secretsmanager_secret" "postgres" {
  name                    = "harmoni/${var.environment}/postgres"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "postgres" {
  secret_id = aws_secretsmanager_secret.postgres.id
  secret_string = jsonencode({
    username = var.db_username
    password = random_password.postgres.result
    dbname   = var.db_name
    host     = aws_db_instance.main.address
    port     = aws_db_instance.main.port
  })
}

resource "aws_db_subnet_group" "main" {
  name       = "harmoni-${var.environment}"
  subnet_ids = var.subnet_ids
  tags       = { Name = "harmoni-${var.environment}-db-subnet-group" }
}

resource "aws_security_group" "rds" {
  name        = "harmoni-${var.environment}-rds"
  description = "harmoni PostgreSQL RDS"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
    description = "PostgreSQL from VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "harmoni-${var.environment}-rds-sg" }
}

resource "aws_db_instance" "main" {
  identifier        = "harmoni-${var.environment}"
  engine            = "postgres"
  engine_version    = "15.7"
  instance_class    = var.instance_class
  allocated_storage = var.allocated_storage
  storage_encrypted = true
  storage_type      = "gp3"

  db_name  = var.db_name
  username = var.db_username
  password = random_password.postgres.result

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]

  backup_retention_period = 7
  backup_window           = "03:00-04:00"
  maintenance_window      = "sun:04:00-sun:05:00"

  deletion_protection = var.environment == "prod"
  skip_final_snapshot = var.environment != "prod"

  performance_insights_enabled = true

  tags = { Name = "harmoni-${var.environment}-postgres" }
}

output "endpoint" { value = aws_db_instance.main.address; sensitive = true }
output "port"     { value = aws_db_instance.main.port }
output "secret_arn" { value = aws_secretsmanager_secret.postgres.arn }
