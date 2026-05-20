terraform {
  backend "s3" {
    bucket = "harmoni-terraform-state"
    key    = "staging/terraform.tfstate"
    region = "us-east-1"
  }
}

module "harmoni" {
  source = "../../"

  environment   = "staging"
  aws_region    = "us-east-1"

  # Smaller instances for staging cost control
  kafka_instance_type           = "kafka.t3.small"
  kafka_broker_count            = 3
  kafka_ebs_volume_size_gb      = 20
  postgres_instance_class       = "db.t3.micro"
  postgres_allocated_storage_gb = 10
}
