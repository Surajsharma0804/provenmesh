#!/bin/bash
# ProvenMesh — AWS EKS Deployment Script
# Prerequisites: AWS CLI, kubectl, eksctl installed
# Usage: ./deploy.sh <AWS_ACCOUNT_ID> <AWS_REGION>

set -euo pipefail

AWS_ACCOUNT_ID="${1:?Usage: ./deploy.sh <AWS_ACCOUNT_ID> <AWS_REGION>}"
AWS_REGION="${2:-us-east-1}"
CLUSTER_NAME="provenmesh-cluster"
ECR_REPO="provenmesh"

echo "╔═══════════════════════════════════════════════════════════╗"
echo "║        ProvenMesh — AWS EKS Deployment                   ║"
echo "║        Account: $AWS_ACCOUNT_ID                          ║"
echo "║        Region:  $AWS_REGION                              ║"
echo "╚═══════════════════════════════════════════════════════════╝"

# ─── Step 1: Create ECR Repository ────────────────────────────────
echo ""
echo "🔧 Step 1: Creating ECR repository..."
aws ecr create-repository \
    --repository-name "$ECR_REPO" \
    --region "$AWS_REGION" \
    2>/dev/null || echo "  ✓ ECR repo already exists"

# ─── Step 2: Build & Push Docker Image ────────────────────────────
echo ""
echo "🐳 Step 2: Building Docker image..."
aws ecr get-login-password --region "$AWS_REGION" | \
    docker login --username AWS --password-stdin \
    "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

docker build -t "$ECR_REPO:latest" .
docker tag "$ECR_REPO:latest" \
    "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
docker push \
    "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO:latest"
echo "  ✓ Image pushed to ECR"

# ─── Step 3: Create EKS Cluster ──────────────────────────────────
echo ""
echo "☸️  Step 3: Creating EKS cluster (this takes 15-20 minutes)..."
eksctl create cluster \
    --name "$CLUSTER_NAME" \
    --region "$AWS_REGION" \
    --nodegroup-name standard-workers \
    --node-type t3.medium \
    --nodes 2 \
    --nodes-min 1 \
    --nodes-max 3 \
    --managed \
    2>/dev/null || echo "  ✓ Cluster already exists"

# Update kubeconfig
aws eks update-kubeconfig --name "$CLUSTER_NAME" --region "$AWS_REGION"
echo "  ✓ kubectl configured"

# ─── Step 4: Replace image placeholders ───────────────────────────
echo ""
echo "📝 Step 4: Updating manifests with your account ID..."
MANIFESTS_DIR="k8s"
for f in "$MANIFESTS_DIR"/*.yaml; do
    sed -i "s|YOUR_AWS_ACCOUNT_ID|$AWS_ACCOUNT_ID|g" "$f"
    sed -i "s|us-east-1|$AWS_REGION|g" "$f"
done
echo "  ✓ Manifests updated"

# ─── Step 5: Deploy to Kubernetes ─────────────────────────────────
echo ""
echo "🚀 Step 5: Deploying to Kubernetes..."
kubectl apply -f "$MANIFESTS_DIR/00-namespace.yaml"
kubectl apply -f "$MANIFESTS_DIR/01-secrets.yaml"
kubectl apply -f "$MANIFESTS_DIR/02-configmap.yaml"
kubectl apply -f "$MANIFESTS_DIR/03-postgres.yaml"
kubectl apply -f "$MANIFESTS_DIR/04-redis.yaml"

# Wait for infra to be ready
echo "  ⏳ Waiting for PostgreSQL and Redis..."
kubectl wait --for=condition=ready pod \
    -l component=postgres \
    -n provenmesh \
    --timeout=120s
kubectl wait --for=condition=ready pod \
    -l component=redis \
    -n provenmesh \
    --timeout=60s

# Deploy workers
kubectl apply -f "$MANIFESTS_DIR/05-workers.yaml"
kubectl apply -f "$MANIFESTS_DIR/06-jobs.yaml"

# Run migrations
echo "  ⏳ Running database migrations..."
kubectl wait --for=condition=complete job/db-migrate \
    -n provenmesh \
    --timeout=120s 2>/dev/null || true

echo ""
echo "╔═══════════════════════════════════════════════════════════╗"
echo "║  ✅ ProvenMesh deployed successfully!                     ║"
echo "║                                                           ║"
echo "║  Check status:  kubectl get pods -n provenmesh            ║"
echo "║  View logs:     kubectl logs -f deploy/crawler-worker     ║"
echo "║                     -n provenmesh                         ║"
echo "║  Scale workers: kubectl scale deploy/crawler-worker       ║"
echo "║                     --replicas=3 -n provenmesh            ║"
echo "╚═══════════════════════════════════════════════════════════╝"
