locals {
  effective_admin_password = var.enable_auth ? (var.admin_password != "" ? var.admin_password : random_password.admin[0].result) : ""
  bind_ip                  = var.allow_external_connections ? "0.0.0.0" : "127.0.0.1"
  instance_name            = "${var.name}-vm"
}

resource "random_password" "admin" {
  count = var.enable_auth && var.admin_password == "" ? 1 : 0

  length  = 24
  special = true
}

resource "google_compute_address" "ip" {
  name    = "${var.name}-ip"
  project = var.project_id
  region  = var.region

  labels = var.labels
}

resource "google_compute_instance" "mongodb" {
  name         = local.instance_name
  project      = var.project_id
  zone         = var.zone
  machine_type = var.machine_type

  tags   = var.tags
  labels = var.labels

  boot_disk {
    initialize_params {
      image = "projects/ubuntu-os-cloud/global/images/family/ubuntu-2204-lts"
      size  = var.disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    network    = var.network
    subnetwork = var.subnetwork

    access_config {
      nat_ip = google_compute_address.ip.address
    }
  }

  service_account {
    email  = var.service_account_email != "" ? var.service_account_email : null
    scopes = var.service_account_scopes
  }

  metadata = {
    startup-script = templatefile("${path.module}/startup.sh.tftpl", {
      mongodb_major_version = var.mongodb_major_version
      bind_ip               = local.bind_ip
      enable_auth           = var.enable_auth
      admin_username        = var.admin_username
      admin_password        = local.effective_admin_password
    })
  }
}

resource "google_compute_firewall" "mongodb" {
  count = var.allow_external_connections && var.create_firewall_rule ? 1 : 0

  name    = "${var.name}-allow-mongodb"
  project = var.project_id
  network = var.network

  direction = "INGRESS"
  priority  = 1000

  source_ranges = length(var.allowed_cidrs) > 0 ? var.allowed_cidrs : ["0.0.0.0/0"]
  target_tags   = var.tags

  allow {
    protocol = "tcp"
    ports    = ["27017"]
  }
}

