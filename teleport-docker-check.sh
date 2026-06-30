#!/usr/bin/env zsh

# Teleport 환경에서 모든 노드의 도커 현황을 일괄 조회하는 스크립트
for node in $(tsh ls --format=names); do 
  echo "\n=== SERVER: $node ==="
  tsh ssh root@$node "docker ps -a"
done
