#!/bin/bash
docker rm -f tlspack_node_service
docker network disconnect --force host tlspack_node_service
docker run --network=host --name tlspack_node_service --volume="$1:/rundir" -it -d --rm tlspack/node:latest /bin/bash
docker exec -d -w / tlspack_node_service python3 -m rundir.NodeService "$1"

