terraform {
  backend "s3" {
    bucket = "harmoni-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
  }
}

module "harmoni" {
  source = "../../"

  environment = "prod"
  aws_region  = "us-east-1"

  # Production-grade sizing
  kafka_instance_type           = "kafka.m5.large"
  kafka_broker_count            = 3
  kafka_ebs_volume_size_gb      = 100
  postgres_instance_class       = "db.r6g.large"
  postgres_allocated_storage_gb = 100
}
