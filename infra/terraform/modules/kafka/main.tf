variable "environment"        { type = string }
variable "vpc_id"             { type = string }
variable "subnet_ids"         { type = list(string) }
variable "kafka_version"      { type = string }
variable "instance_type"      { type = string }
variable "broker_count"       { type = number }
variable "ebs_volume_size_gb" { type = number }

resource "aws_security_group" "msk" {
  name        = "harmoni-${var.environment}-msk"
  description = "harmoni MSK cluster"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 9094
    to_port     = 9094
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
    description = "Kafka TLS (SASL_SSL)"
  }

  ingress {
    from_port   = 2181
    to_port     = 2181
    protocol    = "tcp"
    cidr_blocks = ["10.0.0.0/8"]
    description = "Zookeeper"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "harmoni-${var.environment}-msk-sg" }
}

resource "aws_msk_cluster" "main" {
  cluster_name           = "harmoni-${var.environment}"
  kafka_version          = var.kafka_version
  number_of_broker_nodes = var.broker_count

  broker_node_group_info {
    instance_type  = var.instance_type
    client_subnets = var.subnet_ids
    security_groups = [aws_security_group.msk.id]

    storage_info {
      ebs_storage_info {
        volume_size = var.ebs_volume_size_gb
      }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  logging {
    broker_logs {
      cloudwatch_logs {
        enabled   = true
        log_group = "/harmoni/${var.environment}/msk"
      }
    }
  }

  tags = { Name = "harmoni-${var.environment}-msk" }
}

resource "aws_cloudwatch_log_group" "msk" {
  name              = "/harmoni/${var.environment}/msk"
  retention_in_days = 30
}

output "bootstrap_brokers_tls"    { value = aws_msk_cluster.main.bootstrap_brokers_tls }
output "zookeeper_connect_string" { value = aws_msk_cluster.main.zookeeper_connect_string }
