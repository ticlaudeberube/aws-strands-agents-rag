#!/usr/bin/env bash
# Build the serverless Lambda deployment package (arm64 / Graviton2).
#
# Produces infrastructure/lambda/dist/lambda.zip containing:
#   - the serverless-runtime dependencies from requirements-lambda.txt, built
#     for linux/arm64 (manylinux2014_aarch64) so native wheels match the
#     python3.12 arm64 Lambda runtime regardless of the build host, and
#   - the project's src/ tree.
#
# It also writes dist/lambda.zip.sha256 (base64 SHA-256) for Terraform's
# source_code_hash. Pass the two to Terraform on apply, e.g.:
#   terraform apply \
#     -var "lambda_package_path=$(pwd)/infrastructure/lambda/dist/lambda.zip" \
#     -var "lambda_source_code_hash=$(cat infrastructure/lambda/dist/lambda.zip.sha256)"
#
# Usage: infrastructure/lambda/build_lambda_package.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
BUILD_DIR="$HERE/build"
DIST_DIR="$HERE/dist"
ZIP_PATH="$DIST_DIR/lambda.zip"

echo "==> Cleaning build dir"
rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR" "$DIST_DIR"

echo "==> Installing arm64 runtime deps into build dir"
# --platform + --only-binary pulls prebuilt aarch64 wheels so no host emulation
# is needed. python-version pins the ABI to the Lambda runtime (3.12).
python3 -m pip install \
  --platform manylinux2014_aarch64 \
  --implementation cp \
  --python-version 3.12 \
  --only-binary=:all: \
  --target "$BUILD_DIR" \
  -r "$HERE/requirements-lambda.txt"

echo "==> Copying application source (src/)"
cp -r "$REPO_ROOT/src" "$BUILD_DIR/src"

echo "==> Zipping deployment package"
( cd "$BUILD_DIR" && zip -qr "$ZIP_PATH" . -x '*.pyc' -x '*/__pycache__/*' )

echo "==> Computing base64 SHA-256 (for Terraform source_code_hash)"
# openssl is available on macOS and the CI runner; produces the same base64
# digest Terraform's filebase64sha256() would.
openssl dgst -sha256 -binary "$ZIP_PATH" | openssl base64 > "$DIST_DIR/lambda.zip.sha256"

echo "==> Done:"
echo "    package : $ZIP_PATH ($(du -h "$ZIP_PATH" | cut -f1))"
echo "    sha256  : $(cat "$DIST_DIR/lambda.zip.sha256")"
