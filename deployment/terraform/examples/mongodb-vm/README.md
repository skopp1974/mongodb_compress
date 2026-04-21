# MongoDB VM (GCE) example

This example provisions a single GCE VM, installs MongoDB via `mongodb-org`, and starts `mongod` via systemd.

## Deploy

From this directory:

```bash
terraform init
terraform apply
```

### Required variables

- `project_id`
- `network`
- `subnetwork`

You can pass them via `-var`, `terraform.tfvars`, or environment.

## Uninstall / teardown

### Remove everything created by Terraform

From this directory:

```bash
terraform destroy
```

This deletes the VM, static external IP, and (if enabled) the firewall rule.

### Uninstall MongoDB on an existing VM (optional)

Only needed if you want to remove MongoDB **without** deleting the VM.

```bash
sudo systemctl stop mongod
sudo apt-get purge -y "mongodb-org*"
sudo rm -f /etc/apt/sources.list.d/mongodb-org.list /etc/apt/keyrings/mongodb-server.gpg
sudo apt-get autoremove -y
```

If you also want to remove data and logs (irreversible):

```bash
sudo rm -rf /var/lib/mongodb /var/log/mongodb
```

## Notes

- By default MongoDB binds to `127.0.0.1` (no external connections).
- Set `allow_external_connections=true` and `allowed_cidrs=["X.X.X.X/32"]` to open access.
- If `enable_auth=true` (default), an admin user is created and authorization is enabled.

