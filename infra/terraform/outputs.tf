output "vpc_id" {
  description = "ID of the harmoni VPC"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = module.vpc.private_subnet_ids
}

output "kafka_bootstrap_brokers" {
  description = "MSK bootstrap broker string (TLS)"
  value       = module.kafka.bootstrap_brokers_tls
  sensitive   = true
}

output "kafka_zookeeper_connect" {
  description = "MSK Zookeeper connection string"
  value       = module.kafka.zookeeper_connect_string
  sensitive   = true
}

output "postgres_endpoint" {
  description = "RDS endpoint hostname"
  value       = module.postgres.endpoint
  sensitive   = true
}

output "postgres_port" {
  description = "RDS port"
  value       = module.postgres.port
}
