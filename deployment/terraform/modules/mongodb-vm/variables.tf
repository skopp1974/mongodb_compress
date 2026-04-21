variable "project_id" {
  type        = string
  description = "GCP project id to deploy into."
}

variable "region" {
  type        = string
  description = "GCP region for ancillary resources (e.g. address)."
}

variable "zone" {
  type        = string
  description = "GCP zone for the VM."
}

variable "name" {
  type        = string
  description = "Base name for MongoDB resources."
  default     = "mongodb"
}

variable "network" {
  type        = string
  description = "VPC network self_link or name (same project) for the VM."
}

variable "subnetwork" {
  type        = string
  description = "Subnetwork self_link or name (same region/project) for the VM."
}

variable "machine_type" {
  type        = string
  description = "GCE machine type."
  default     = "e2-standard-2"
}

variable "disk_size_gb" {
  type        = number
  description = "Boot disk size in GB."
  default     = 50
}

variable "mongodb_major_version" {
  type        = string
  description = "MongoDB major version to install via mongodb-org (e.g. 7.0)."
  default     = "7.0"
}

variable "allow_external_connections" {
  type        = bool
  description = "If true, MongoDB binds on 0.0.0.0 and a firewall rule can be created."
  default     = false
}

variable "allowed_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to reach port 27017 when allow_external_connections is true."
  default     = []
}

variable "create_firewall_rule" {
  type        = bool
  description = "If true and allow_external_connections is true, create a VPC firewall rule allowing port 27017 from allowed_cidrs."
  default     = true
}

variable "enable_auth" {
  type        = bool
  description = "If true, creates an admin user on first boot and enables security.authorization."
  default     = true
}

variable "admin_username" {
  type        = string
  description = "Admin username to create when enable_auth is true."
  default     = "admin"
}

variable "admin_password" {
  type        = string
  description = "Optional admin password. If empty and enable_auth is true, a random password is generated."
  default     = ""
  sensitive   = true
}

variable "tags" {
  type        = list(string)
  description = "Network tags to apply to the instance."
  default     = ["mongodb"]
}

variable "service_account_email" {
  type        = string
  description = "Optional service account email to attach to the VM. If empty, uses default compute service account."
  default     = ""
}

variable "service_account_scopes" {
  type        = list(string)
  description = "OAuth scopes for the instance service account."
  default     = ["https://www.googleapis.com/auth/cloud-platform"]
}

variable "labels" {
  type        = map(string)
  description = "Labels to apply to resources."
  default     = {}
}

