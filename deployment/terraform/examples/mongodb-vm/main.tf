provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}

module "mongodb" {
  source = "../../modules/mongodb-vm"

  project_id = var.project_id
  region     = var.region
  zone       = var.zone

  name       = var.name
  network    = var.network
  subnetwork = var.subnetwork

  machine_type = var.machine_type
  disk_size_gb = var.disk_size_gb

  mongodb_major_version      = var.mongodb_major_version
  allow_external_connections = var.allow_external_connections
  allowed_cidrs              = var.allowed_cidrs
  create_firewall_rule       = var.create_firewall_rule

  enable_auth    = var.enable_auth
  admin_username = var.admin_username
  admin_password = var.admin_password

  service_account_email  = var.service_account_email
  service_account_scopes = var.service_account_scopes

  tags   = var.tags
  labels = var.labels
}

output "mongodb_external_ip" {
  value = module.mongodb.external_ip
}

output "mongodb_admin_username" {
  value = module.mongodb.admin_username
}

output "mongodb_admin_password" {
  value     = module.mongodb.admin_password
  sensitive = true
}

