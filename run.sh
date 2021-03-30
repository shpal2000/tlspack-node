#!/bin/bash
docker rm -f tlspack_node_rpc
docker network disconnect --force host tlspack_node_rpc
docker run --network=host --name tlspack_node_rpc --volume="$1:/rundir" -it -d --rm tlspack/node:latest /bin/bash
docker exec -d -w /rundir tlspack_node_rpc python3 -m tlspack-node.NodeService "$1"

