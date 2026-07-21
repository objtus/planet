#!/usr/bin/env bash
# Docker bridge からホスト上の MCP ポート (9311 等) へ到達させる。
# コンテナ → 172.20.0.1 は FORWARD ではなく INPUT に入るため両方にルールを追加。
#
#   sudo ./scripts/mcp-firewall-docker.sh 9311
set -euo pipefail
PORT="${1:-9311}"
CHAIN=DOCKER-USER
CIDRS=("172.20.0.0/16" "172.17.0.0/16")

if ! sudo iptables -L "$CHAIN" -n &>/dev/null; then
  echo "Creating $CHAIN chain..."
  sudo iptables -N "$CHAIN" 2>/dev/null || true
  sudo iptables -C FORWARD -j "$CHAIN" 2>/dev/null || sudo iptables -I FORWARD 1 -j "$CHAIN"
fi

add_rule() {
  local table_chain=$1
  shift
  if sudo iptables -C "$table_chain" "$@" 2>/dev/null; then
    echo "Already exists ($table_chain): $*"
  else
    sudo iptables -I "$table_chain" 1 "$@"
    echo "Added ($table_chain): $*"
  fi
}

for cidr in "${CIDRS[@]}"; do
  add_rule "$CHAIN" -s "$cidr" -d 172.20.0.1 -p tcp --dport "$PORT" -j ACCEPT
  add_rule INPUT -s "$cidr" -p tcp --dport "$PORT" -j ACCEPT
done

# hermes-webui ブリッジ IF（172.20.0.1）が分かれば INPUT に interface 指定も追加
IFACE=$(ip -4 route show dev br-92cb2f06b921 2>/dev/null | awk 'NR==1{print $3; exit}')
IFACE=${IFACE:-br-92cb2f06b921}
if ip link show "$IFACE" &>/dev/null; then
  add_rule INPUT -i "$IFACE" -p tcp --dport "$PORT" -j ACCEPT
fi

echo "Done. Test from container:"
echo "  docker exec hermes-webui-hermes-webui-1 python3 -c \"import socket; s=socket.create_connection(('172.20.0.1',$PORT),3); print('OK')\""
