#!/usr/bin/env bash
set -euo pipefail

# ---------- Create directory structure ----------
mkdir -p /opt/firecracker/{rootfs-cache,vms,kernel,ssh}

# ---------- Install Firecracker v1.6.0 ----------
ARCH="$(uname -m)"
FC_VERSION="v1.6.0"
FC_URL="https://github.com/firecracker-microvm/firecracker/releases/download/$${FC_VERSION}/firecracker-$${FC_VERSION}-$${ARCH}.tgz"

curl -fSL "$${FC_URL}" -o /tmp/firecracker.tgz
tar -xzf /tmp/firecracker.tgz -C /tmp
mv /tmp/release-$${FC_VERSION}-$${ARCH}/firecracker-$${FC_VERSION}-$${ARCH} /usr/local/bin/firecracker
chmod +x /usr/local/bin/firecracker
rm -rf /tmp/firecracker.tgz /tmp/release-$${FC_VERSION}-$${ARCH}

# ---------- Verify KVM support ----------
if [ ! -e /dev/kvm ]; then
  echo "ERROR: /dev/kvm not found. Bare-metal instance required." >&2
  exit 1
fi

# ---------- Generate SSH key pair ----------
ssh-keygen -t ed25519 -f /opt/firecracker/ssh/id_ed25519 -N "" -C "firecracker-orchestrator"

# ---------- Download kernel from S3 ----------
aws s3 cp "s3://${s3_bucket}/kernel/vmlinux" /opt/firecracker/kernel/vmlinux --region "${region}"
chmod 644 /opt/firecracker/kernel/vmlinux

# ---------- Enable IP forwarding ----------
sysctl -w net.ipv4.ip_forward=1
echo "net.ipv4.ip_forward=1" >> /etc/sysctl.d/99-firecracker.conf

# ---------- Install Python 3.12 and pip ----------
dnf install -y python3.12 python3.12-pip

# ---------- Create orchestrator systemd service ----------
cat > /etc/systemd/system/orchestrator.service <<'EOF'
[Unit]
Description=Firecracker Sandbox Orchestrator
After=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3.12 -m orchestrator
WorkingDirectory=/opt/firecracker
Restart=on-failure
RestartSec=5
Environment=FIRECRACKER_BIN=/usr/local/bin/firecracker
Environment=KERNEL_PATH=/opt/firecracker/kernel/vmlinux
Environment=ROOTFS_DIR=/opt/firecracker/rootfs-cache
Environment=VM_DIR=/opt/firecracker/vms
Environment=SSH_KEY_PATH=/opt/firecracker/ssh/id_ed25519

[Install]
WantedBy=multi-user.target
EOF

# ---------- Enable and start the orchestrator ----------
systemctl daemon-reload
systemctl enable orchestrator.service
systemctl start orchestrator.service
