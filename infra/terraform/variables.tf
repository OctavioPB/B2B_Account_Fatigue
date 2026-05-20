variable "environment" {
  description = "Deployment environment (staging | prod)"
  type        = string
  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be 'staging' or 'prod'."
  }
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

# --- Networking ---

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of AZs to use (must have at least 2 for MSK)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (NAT gateways)"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

# --- Kafka (MSK) ---

variable "kafka_version" {
  description = "Apache Kafka version for MSK cluster"
  type        = string
  default     = "3.6.0"
}

variable "kafka_instance_type" {
  description = "MSK broker instance type"
  type        = string
  default     = "kafka.m5.large"
}

variable "kafka_broker_count" {
  description = "Number of MSK broker nodes (must be divisible by AZ count)"
  type        = number
  default     = 3
}

variable "kafka_ebs_volume_size_gb" {
  description = "EBS volume size per broker in GiB"
  type        = number
  default     = 100
}

# --- PostgreSQL (RDS) ---

variable "postgres_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.medium"
}

variable "postgres_allocated_storage_gb" {
  description = "Initial allocated storage in GiB"
  type        = number
  default     = 20
}

variable "postgres_username" {
  description = "Master username for the RDS instance"
  type        = string
  default     = "harmoni"
  sensitive   = true
}
