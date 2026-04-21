output "instance_name" {
  value       = google_compute_instance.mongodb.name
  description = "Name of the VM instance running MongoDB."
}

output "external_ip" {
  value       = google_compute_address.ip.address
  description = "External IP address of the VM."
}

output "connection_host" {
  value       = google_compute_address.ip.address
  description = "Host to use for MongoDB connection (external IP)."
}

output "connection_port" {
  value       = 27017
  description = "MongoDB port."
}

output "admin_username" {
  value       = var.enable_auth ? var.admin_username : ""
  description = "Admin username (when enable_auth is true)."
}

output "admin_password" {
  value       = var.enable_auth ? local.effective_admin_password : ""
  description = "Admin password (when enable_auth is true)."
  sensitive   = true
}

