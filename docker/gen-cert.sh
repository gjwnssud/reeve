#!/bin/bash
# Self-signed 인증서 생성 (IP SAN 포함)
# 사용법: ./gen-cert.sh <SERVER_IP>
#   예시: ./gen-cert.sh 192.168.1.100

set -e

IP="${1:-$(hostname -I | awk '{print $1}')}"
CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"

mkdir -p "$CERT_DIR"

openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
  -keyout "$CERT_DIR/key.pem" \
  -out   "$CERT_DIR/cert.pem" \
  -subj  "/CN=$IP" \
  -addext "subjectAltName=IP:$IP,IP:127.0.0.1"

chmod 600 "$CERT_DIR/key.pem"
echo ""
echo "인증서 생성 완료 (유효기간 10년)"
echo "  위치: $CERT_DIR"
echo "  대상 IP: $IP"
echo ""
echo "브라우저 접속 시 보안 경고 → 고급 → 계속 진행(안전하지 않음)으로 수락하세요."
