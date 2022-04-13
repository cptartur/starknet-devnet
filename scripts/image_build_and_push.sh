#!/bin/bash
set -e

[ -f .env ] && source .env

IMAGE=shardlabs/starknet-devnet
LOCAL_VERSION=$(./scripts/get_version.sh version)
echo "Local version: $LOCAL_VERSION"

echo "Build image regardless of versioning"
docker build -t "$IMAGE:$LOCAL_VERSION" -t "$IMAGE:latest" .

echo "Run a devnet instance in background; sleep to allow it to start"
# can't use "localhost" because docker doesn't allow such mapping
docker run -d -p 127.0.0.1:5050:5050 --name devnet "$IMAGE:latest"
sleep 10
docker logs devnet

echo "Checking if devnet instance is alive"
ssh remote-docker curl localhost:5050/is_alive

# curling the url fails with 404
function docker_image_exists() {
    curl --silent -f -lSL "$1" > /dev/null 2>&1
}

function log_already_pushed() {
    echo "Latest Docker Hub version is already equal to the local version."
    echo "Pushing skipped"
}

function push() {
    docker login --username "$DOCKER_USER" --password "$DOCKER_PASS"
    docker push "$IMAGE:$LOCAL_VERSION"
    docker push "$IMAGE:latest"
}

dockerhub_url="https://hub.docker.com/v2/repositories/$IMAGE/tags/$LOCAL_VERSION"
docker_image_exists "$dockerhub_url" && log_already_pushed || push
