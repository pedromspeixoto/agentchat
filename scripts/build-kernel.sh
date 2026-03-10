#!/bin/bash
set -euo pipefail

KERNEL_URL="https://github.com/firecracker-microvm/firecracker/releases/download/v1.5.1/vmlinux-5.10.204"
BUILD_DIR="./build"
KERNEL_PATH="${BUILD_DIR}/vmlinux"
S3_BUCKET="${1:-}"

usage() {
    echo "Usage: $0 [s3-bucket-name]"
    echo ""
    echo "Downloads a prebuilt Firecracker-compatible Linux kernel (v5.10)."
    echo "Places it at ${KERNEL_PATH}."
    echo ""
    echo "Options:"
    echo "  s3-bucket-name   Optional. If provided, uploads the kernel to s3://<bucket>/kernel/vmlinux"
    echo ""
    echo "Examples:"
    echo "  $0                      # Download kernel only"
    echo "  $0 my-rootfs-bucket     # Download and upload to S3"
    exit 1
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
fi

echo "==> Creating build directory..."
mkdir -p "${BUILD_DIR}"

echo "==> Downloading Firecracker-compatible kernel (v5.10)..."
curl -fSL -o "${KERNEL_PATH}" "${KERNEL_URL}"
chmod +x "${KERNEL_PATH}"

echo "==> Kernel downloaded to ${KERNEL_PATH}"
ls -lh "${KERNEL_PATH}"

if [[ -n "${S3_BUCKET}" ]]; then
    echo "==> Uploading kernel to s3://${S3_BUCKET}/kernel/vmlinux..."
    aws s3 cp "${KERNEL_PATH}" "s3://${S3_BUCKET}/kernel/vmlinux" --only-show-errors
    echo "==> Kernel uploaded to S3 successfully."
fi

echo "==> Done."
