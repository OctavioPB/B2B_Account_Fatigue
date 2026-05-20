terraform {
  required_version = ">= 1.8"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # Remote state — configure backend per environment (see environments/)
  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "harmoni"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

# ---------------------------------------------------------------------------
# VPC
# ---------------------------------------------------------------------------
module "vpc" {
  source = "./modules/vpc"

  environment      = var.environment
  vpc_cidr         = var.vpc_cidr
  azs              = var.availability_zones
  private_subnets  = var.private_subnet_cidrs
  public_subnets   = var.public_subnet_cidrs
}

# ---------------------------------------------------------------------------
# Managed Kafka (MSK)
# ---------------------------------------------------------------------------
module "kafka" {
  source = "./modules/kafka"

  environment        = var.environment
  vpc_id             = module.vpc.vpc_id
  subnet_ids         = module.vpc.private_subnet_ids
  kafka_version      = var.kafka_version
  instance_type      = var.kafka_instance_type
  broker_count       = var.kafka_broker_count
  ebs_volume_size_gb = var.kafka_ebs_volume_size_gb
}

# ---------------------------------------------------------------------------
# Managed PostgreSQL (RDS)
# ---------------------------------------------------------------------------
module "postgres" {
  source = "./modules/postgres"

  environment       = var.environment
  vpc_id            = module.vpc.vpc_id
  subnet_ids        = module.vpc.private_subnet_ids
  instance_class    = var.postgres_instance_class
  allocated_storage = var.postgres_allocated_storage_gb
  db_name           = "harmoni"
  db_username       = var.postgres_username
}
