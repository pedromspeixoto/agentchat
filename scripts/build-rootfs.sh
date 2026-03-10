#!/bin/bash
set -euo pipefail

DOCKER_IMAGE="${1:-}"
OUTPUT_PATH="${2:-./build/rootfs.ext4}"
ROOTFS_SIZE_MB="${ROOTFS_SIZE_MB:-1024}"

usage() {
    echo "Usage: $0 <docker-image> [output-path]"
    echo ""
    echo "Converts a Docker image into a Firecracker-compatible ext4 rootfs."
    echo ""
    echo "Arguments:"
    echo "  docker-image   Required. Docker image to convert (e.g. python:3.12-slim)"
    echo "  output-path    Optional. Output path for the ext4 image (default: ./build/rootfs.ext4)"
    echo ""
    echo "Environment variables:"
    echo "  SSH_PUBLIC_KEY    SSH public key to inject. Falls back to ~/.ssh/id_rsa.pub"
    echo "  ROOTFS_SIZE_MB   Size of the rootfs image in MB (default: 1024)"
    echo ""
    echo "Examples:"
    echo "  $0 python:3.12-slim"
    echo "  $0 ubuntu:22.04 ./build/my-rootfs.ext4"
    echo "  SSH_PUBLIC_KEY=\"ssh-rsa AAAA...\" $0 python:3.12-slim"
    exit 1
}

if [[ -z "${DOCKER_IMAGE}" || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
fi

BUILD_DIR="$(dirname "${OUTPUT_PATH}")"
TMPDIR="$(mktemp -d)"
ROOTFS_MNT="$(mktemp -d)"

cleanup() {
    echo "==> Cleaning up temporary files..."
    if mountpoint -q "${ROOTFS_MNT}" 2>/dev/null; then
        umount "${ROOTFS_MNT}" || true
    fi
    rm -rf "${TMPDIR}" "${ROOTFS_MNT}"
    if [[ -n "${CONTAINER_ID:-}" ]]; then
        docker rm -f "${CONTAINER_ID}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

echo "==> Creating build directory..."
mkdir -p "${BUILD_DIR}"

# Pull the Docker image
echo "==> Pulling Docker image: ${DOCKER_IMAGE}..."
docker pull "${DOCKER_IMAGE}"

# Create a container and export its filesystem
echo "==> Creating container and exporting filesystem..."
CONTAINER_ID=$(docker create "${DOCKER_IMAGE}")
docker export "${CONTAINER_ID}" -o "${TMPDIR}/rootfs.tar"
docker rm -f "${CONTAINER_ID}" > /dev/null
unset CONTAINER_ID

# Extract the filesystem
echo "==> Extracting filesystem..."
mkdir -p "${TMPDIR}/rootfs"
tar -xf "${TMPDIR}/rootfs.tar" -C "${TMPDIR}/rootfs"
rm -f "${TMPDIR}/rootfs.tar"

# Inject overlay-init script
echo "==> Injecting /sbin/overlay-init..."
cat > "${TMPDIR}/rootfs/sbin/overlay-init" << 'OVERLAY_INIT'
#!/bin/bash

# Mount essential filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts

# Set hostname
hostname sandbox

# Configure networking from kernel cmdline or use defaults
CMDLINE=$(cat /proc/cmdline)
IP_ADDR="172.16.0.2/30"
GATEWAY="172.16.0.1"

# Parse ip= from kernel cmdline if present (format: ip=<addr>::<gw>:<mask>::<iface>:off)
if echo "${CMDLINE}" | grep -qo 'ip=[^ ]*'; then
    IP_PARAM=$(echo "${CMDLINE}" | grep -o 'ip=[^ ]*' | head -1 | cut -d= -f2)
    PARSED_IP=$(echo "${IP_PARAM}" | cut -d: -f1)
    PARSED_GW=$(echo "${IP_PARAM}" | cut -d: -f3)
    if [[ -n "${PARSED_IP}" ]]; then
        IP_ADDR="${PARSED_IP}"
    fi
    if [[ -n "${PARSED_GW}" ]]; then
        GATEWAY="${PARSED_GW}"
    fi
fi

# Bring up networking
ip link set dev lo up
ip link set dev eth0 up
ip addr add "${IP_ADDR}" dev eth0
ip route add default via "${GATEWAY}" dev eth0

# Set up DNS
echo "nameserver 8.8.8.8" > /etc/resolv.conf

# Start sshd if available
if [[ -x /usr/sbin/sshd ]]; then
    mkdir -p /run/sshd
    /usr/sbin/sshd
fi

# Exec into shell or init
if [[ -x /sbin/init ]]; then
    exec /sbin/init
else
    exec /bin/bash
fi
OVERLAY_INIT
chmod +x "${TMPDIR}/rootfs/sbin/overlay-init"

# Install openssh-server via chroot
echo "==> Installing openssh-server in rootfs..."
# Mount required filesystems for chroot
mount --bind /proc "${TMPDIR}/rootfs/proc"
mount --bind /sys "${TMPDIR}/rootfs/sys"
mount --bind /dev "${TMPDIR}/rootfs/dev"

chroot "${TMPDIR}/rootfs" /bin/bash -c "apt-get update && apt-get install -y openssh-server" || {
    echo "WARNING: Failed to install openssh-server (image may not be Debian/Ubuntu-based)."
}

umount "${TMPDIR}/rootfs/proc" || true
umount "${TMPDIR}/rootfs/sys" || true
umount "${TMPDIR}/rootfs/dev" || true

# Configure sshd
echo "==> Configuring sshd..."
if [[ -f "${TMPDIR}/rootfs/etc/ssh/sshd_config" ]]; then
    sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' "${TMPDIR}/rootfs/etc/ssh/sshd_config"
fi
mkdir -p "${TMPDIR}/rootfs/run/sshd"

# Inject SSH public key
echo "==> Injecting SSH public key..."
SSH_KEY="${SSH_PUBLIC_KEY:-}"
if [[ -z "${SSH_KEY}" && -f "${HOME}/.ssh/id_rsa.pub" ]]; then
    SSH_KEY=$(cat "${HOME}/.ssh/id_rsa.pub")
fi

if [[ -n "${SSH_KEY}" ]]; then
    mkdir -p "${TMPDIR}/rootfs/root/.ssh"
    echo "${SSH_KEY}" > "${TMPDIR}/rootfs/root/.ssh/authorized_keys"
    chmod 700 "${TMPDIR}/rootfs/root/.ssh"
    chmod 600 "${TMPDIR}/rootfs/root/.ssh/authorized_keys"
    echo "    SSH public key injected."
else
    echo "WARNING: No SSH public key found. Set SSH_PUBLIC_KEY or ensure ~/.ssh/id_rsa.pub exists."
fi

# Create ext4 image
echo "==> Creating ext4 rootfs image (${ROOTFS_SIZE_MB}MB)..."
dd if=/dev/zero of="${OUTPUT_PATH}" bs=1M count="${ROOTFS_SIZE_MB}" status=progress
mkfs.ext4 "${OUTPUT_PATH}"

echo "==> Mounting and copying filesystem..."
mount -o loop "${OUTPUT_PATH}" "${ROOTFS_MNT}"
cp -a "${TMPDIR}/rootfs/." "${ROOTFS_MNT}/"
umount "${ROOTFS_MNT}"

echo "==> Rootfs created at ${OUTPUT_PATH}"
ls -lh "${OUTPUT_PATH}"
echo "==> Done."
