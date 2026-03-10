#!/bin/bash
set -euo pipefail

S3_BUCKET="${1:-}"

usage() {
    echo "Usage: $0 <s3-bucket-name>"
    echo ""
    echo "Uploads the built rootfs and kernel to an S3 bucket."
    echo ""
    echo "Arguments:"
    echo "  s3-bucket-name   Required. The S3 bucket to upload to."
    echo ""
    echo "Uploads:"
    echo "  ./build/rootfs.ext4  -> s3://<bucket>/rootfs/rootfs.ext4"
    echo "  ./build/vmlinux      -> s3://<bucket>/kernel/vmlinux"
    echo ""
    echo "Examples:"
    echo "  $0 my-rootfs-bucket"
    exit 1
}

if [[ -z "${S3_BUCKET}" || "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    usage
fi

ROOTFS_PATH="./build/rootfs.ext4"
KERNEL_PATH="./build/vmlinux"

# Verify files exist
if [[ ! -f "${ROOTFS_PATH}" ]]; then
    echo "ERROR: Rootfs not found at ${ROOTFS_PATH}. Run build-rootfs.sh first."
    exit 1
fi

if [[ ! -f "${KERNEL_PATH}" ]]; then
    echo "ERROR: Kernel not found at ${KERNEL_PATH}. Run build-kernel.sh first."
    exit 1
fi

echo "==> Uploading rootfs to s3://${S3_BUCKET}/rootfs/rootfs.ext4..."
aws s3 cp "${ROOTFS_PATH}" "s3://${S3_BUCKET}/rootfs/rootfs.ext4" --only-show-errors

echo "==> Uploading kernel to s3://${S3_BUCKET}/kernel/vmlinux..."
aws s3 cp "${KERNEL_PATH}" "s3://${S3_BUCKET}/kernel/vmlinux" --only-show-errors

echo "==> All artifacts uploaded to s3://${S3_BUCKET}/ successfully."
echo "==> Done."
