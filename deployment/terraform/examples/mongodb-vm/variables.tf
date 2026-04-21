variable "project_id" {
  type        = string
  description = "GCP project id."
}

variable "region" {
  type        = string
  description = "GCP region."
  default     = "us-central1"
}

variable "zone" {
  type        = string
  description = "GCP zone."
  default     = "us-central1-a"
}

variable "name" {
  type        = string
  description = "Base name for MongoDB resources."
  default     = "mongodb"
}

variable "network" {
  type        = string
  description = "VPC network self_link or name."
}

variable "subnetwork" {
  type        = string
  description = "Subnetwork self_link or name."
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
  description = "MongoDB major version (e.g. 7.0)."
  default     = "7.0"
}

variable "allow_external_connections" {
  type        = bool
  description = "If true, MongoDB binds on 0.0.0.0."
  default     = false
}

variable "allowed_cidrs" {
  type        = list(string)
  description = "CIDRs allowed to reach port 27017."
  default     = []
}

variable "create_firewall_rule" {
  type        = bool
  description = "Create a VPC firewall rule to allow port 27017."
  default     = true
}

variable "enable_auth" {
  type        = bool
  description = "Enable MongoDB authorization and create an admin user."
  default     = true
}

variable "admin_username" {
  type        = string
  description = "Admin username."
  default     = "admin"
}

variable "admin_password" {
  type        = string
  description = "Optional admin password. If empty, one will be generated."
  default     = ""
  sensitive   = true
}

variable "tags" {
  type        = list(string)
  description = "Network tags."
  default     = ["mongodb"]
}

variable "labels" {
  type        = map(string)
  description = "Labels."
  default     = {}
}

variable "service_account_email" {
  type        = string
  description = "Optional service account email to attach to the VM."
  default     = ""
}

variable "service_account_scopes" {
  type        = list(string)
  description = "OAuth scopes for the instance service account."
  default     = ["https://www.googleapis.com/auth/cloud-platform"]
}

