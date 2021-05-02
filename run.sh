#!/bin/bash
docker rm -f TlspackNodeService
docker network disconnect --force host TlspackNodeService
docker run --network=host --name TlspackNodeService --volume="$1:/rundir" -it -d --rm tlspack/node:latest /bin/bash
sleep 1
docker exec -d -w / TlspackNodeService python3 -m rundir.NodeService "$1"
sleep 1
docker exec -d -w / TlspackNodeService python3 -m rundir.NodeStatus "$1"
sleep 5
