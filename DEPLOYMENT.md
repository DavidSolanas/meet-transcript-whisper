# Cloud Deployment Guide

This guide covers deploying the Meeting Transcription API to various cloud platforms with GPU support for production workloads.

## Table of Contents

- [Pre-Deployment Checklist](#pre-deployment-checklist)
- [AWS Deployment](#aws-deployment)
- [Google Cloud Platform](#google-cloud-platform)
- [Azure Deployment](#azure-deployment)
- [Railway / Render (Simple)](#railway--render-simple)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Environment & Secrets](#environment--secrets)
- [Monitoring & Logging](#monitoring--logging)
- [Scaling Considerations](#scaling-considerations)
- [Cost Optimization](#cost-optimization)

---

## Pre-Deployment Checklist

Before deploying, ensure you have:

- [ ] HuggingFace access token with pyannote model access
- [ ] Accepted model terms at [huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [ ] Chosen appropriate Whisper model size for your use case
- [ ] Estimated GPU/CPU requirements based on expected load
- [ ] Set up domain name (optional but recommended)
- [ ] Configured SSL certificates (use Let's Encrypt or cloud provider)

### Resource Requirements

| Workload | Instance Type | GPU | RAM | Storage |
|----------|---------------|-----|-----|---------|
| Development | t3.medium | None | 4GB | 20GB |
| Light (CPU) | c5.2xlarge | None | 16GB | 50GB |
| Production | g4dn.xlarge | T4 | 16GB | 100GB |
| High Volume | g5.2xlarge | A10G | 32GB | 200GB |

---

## AWS Deployment

### Option 1: EC2 with Docker Compose (Simplest)

**1. Launch EC2 Instance**

```bash
# Using AWS CLI
aws ec2 run-instances \
  --image-id ami-0a0e5d9c7acc336f1 \  # Ubuntu 22.04 with NVIDIA drivers
  --instance-type g4dn.xlarge \
  --key-name your-key-pair \
  --security-group-ids sg-xxxxx \
  --subnet-id subnet-xxxxx \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=meet-transcriber}]'
```

**2. Configure Security Group**

```bash
# Allow inbound traffic
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 22 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 80 \
  --cidr 0.0.0.0/0

aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 443 \
  --cidr 0.0.0.0/0
```

**3. Connect and Setup**

```bash
# SSH into instance
ssh -i your-key.pem ubuntu@<instance-ip>

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker ubuntu

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Verify GPU access
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

**4. Deploy Application**

```bash
# Clone repository
git clone https://github.com/yourusername/meet-transcript-whisper.git
cd meet-transcript-whisper

# Create environment file
cat > .env << 'EOF'
HUGGINGFACE_ACCESS_TOKEN=hf_your_token_here
WHISPER_MODEL=base
REDIS_URL=redis://redis:6379/0
LOG_LEVEL=INFO
LOG_JSON=true
PRELOAD_MODELS=true
EOF

# Start services
docker-compose up -d

# Check logs
docker-compose logs -f
```

**5. Setup Nginx Reverse Proxy (Optional)**

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Create Nginx config
sudo tee /etc/nginx/sites-available/meet-transcriber << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 500M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/meet-transcriber /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Setup SSL with Let's Encrypt
sudo certbot --nginx -d your-domain.com
```

### Option 2: AWS ECS with Fargate

**1. Create ECR Repository**

```bash
# Create repository
aws ecr create-repository --repository-name meet-transcriber

# Get login token
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com

# Build and push image
docker build -t meet-transcriber .
docker tag meet-transcriber:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/meet-transcriber:latest
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/meet-transcriber:latest
```

**2. Create ECS Task Definition**

```json
{
  "family": "meet-transcriber",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "4096",
  "memory": "16384",
  "executionRoleArn": "arn:aws:iam::<account-id>:role/ecsTaskExecutionRole",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "<account-id>.dkr.ecr.us-east-1.amazonaws.com/meet-transcriber:latest",
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "REDIS_URL", "value": "redis://your-elasticache-endpoint:6379/0"},
        {"name": "WHISPER_MODEL", "value": "base"},
        {"name": "LOG_JSON", "value": "true"}
      ],
      "secrets": [
        {
          "name": "HUGGINGFACE_ACCESS_TOKEN",
          "valueFrom": "arn:aws:secretsmanager:us-east-1:<account-id>:secret:hf-token"
        }
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/meet-transcriber",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

> **Note:** ECS Fargate does not support GPU. For GPU workloads, use ECS on EC2 with GPU instances.

### Option 3: AWS ECS on EC2 (GPU Support)

```bash
# Create ECS cluster with GPU instances
aws ecs create-cluster --cluster-name meet-transcriber-gpu

# Create launch template for GPU instances
aws ec2 create-launch-template \
  --launch-template-name meet-transcriber-gpu \
  --launch-template-data '{
    "ImageId": "ami-0a0e5d9c7acc336f1",
    "InstanceType": "g4dn.xlarge",
    "UserData": "#!/bin/bash\necho ECS_CLUSTER=meet-transcriber-gpu >> /etc/ecs/ecs.config"
  }'
```

---

## Google Cloud Platform

### Option 1: Compute Engine with Docker

**1. Create VM Instance**

```bash
# Create GPU instance
gcloud compute instances create meet-transcriber \
  --zone=us-central1-a \
  --machine-type=n1-standard-4 \
  --accelerator=type=nvidia-tesla-t4,count=1 \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=100GB \
  --boot-disk-type=pd-ssd \
  --maintenance-policy=TERMINATE \
  --metadata=startup-script='#!/bin/bash
    curl -fsSL https://get.docker.com | sh
    distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
    curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | apt-key add -
    curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list > /etc/apt/sources.list.d/nvidia-docker.list
    apt-get update
    apt-get install -y nvidia-container-toolkit
    systemctl restart docker'
```

**2. Configure Firewall**

```bash
gcloud compute firewall-rules create allow-http \
  --allow=tcp:80,tcp:443,tcp:8000 \
  --target-tags=http-server

gcloud compute instances add-tags meet-transcriber \
  --zone=us-central1-a \
  --tags=http-server
```

**3. Deploy Application**

```bash
# SSH into instance
gcloud compute ssh meet-transcriber --zone=us-central1-a

# Follow same Docker setup as AWS EC2
```

### Option 2: Cloud Run (CPU Only)

Cloud Run is serverless but doesn't support GPUs. Suitable for light workloads.

```bash
# Build and push to Container Registry
gcloud builds submit --tag gcr.io/PROJECT_ID/meet-transcriber

# Deploy to Cloud Run
gcloud run deploy meet-transcriber \
  --image gcr.io/PROJECT_ID/meet-transcriber \
  --platform managed \
  --region us-central1 \
  --memory 8Gi \
  --cpu 4 \
  --timeout 900 \
  --concurrency 1 \
  --max-instances 10 \
  --set-env-vars "WHISPER_MODEL=tiny,LOG_JSON=true" \
  --set-secrets "HUGGINGFACE_ACCESS_TOKEN=hf-token:latest"
```

### Option 3: Google Kubernetes Engine (GKE)

```bash
# Create GKE cluster with GPU node pool
gcloud container clusters create meet-transcriber \
  --zone us-central1-a \
  --num-nodes 1 \
  --machine-type n1-standard-4

# Add GPU node pool
gcloud container node-pools create gpu-pool \
  --cluster meet-transcriber \
  --zone us-central1-a \
  --machine-type n1-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1 \
  --num-nodes 1

# Install NVIDIA drivers
kubectl apply -f https://raw.githubusercontent.com/GoogleCloudPlatform/container-engine-accelerators/master/nvidia-driver-installer/cos/daemonset-preloaded.yaml
```

---

## Azure Deployment

### Option 1: Azure VM with Docker

**1. Create VM**

```bash
# Create resource group
az group create --name meet-transcriber-rg --location eastus

# Create VM with GPU
az vm create \
  --resource-group meet-transcriber-rg \
  --name meet-transcriber \
  --image Ubuntu2204 \
  --size Standard_NC4as_T4_v3 \
  --admin-username azureuser \
  --generate-ssh-keys \
  --os-disk-size-gb 100
```

**2. Configure Network**

```bash
# Open ports
az vm open-port --resource-group meet-transcriber-rg \
  --name meet-transcriber --port 80 --priority 1001

az vm open-port --resource-group meet-transcriber-rg \
  --name meet-transcriber --port 443 --priority 1002

az vm open-port --resource-group meet-transcriber-rg \
  --name meet-transcriber --port 8000 --priority 1003
```

**3. Install NVIDIA Drivers and Docker**

```bash
# SSH into VM
ssh azureuser@<vm-ip>

# Install NVIDIA drivers
sudo apt-get update
sudo apt-get install -y nvidia-driver-535

# Install Docker (same as AWS setup)
curl -fsSL https://get.docker.com | sh
# ... continue with NVIDIA Container Toolkit setup
```

### Option 2: Azure Container Instances (CPU Only)

```bash
# Create container instance
az container create \
  --resource-group meet-transcriber-rg \
  --name meet-transcriber \
  --image youracr.azurecr.io/meet-transcriber:latest \
  --cpu 4 \
  --memory 16 \
  --ports 8000 \
  --environment-variables \
    WHISPER_MODEL=base \
    LOG_JSON=true \
  --secure-environment-variables \
    HUGGINGFACE_ACCESS_TOKEN=hf_your_token
```

---

## Railway / Render (Simple)

For quick deployments without GPU (suitable for demos or light usage).

### Railway

1. Connect your GitHub repository to Railway
2. Add environment variables in the Railway dashboard:
   - `HUGGINGFACE_ACCESS_TOKEN`
   - `WHISPER_MODEL=tiny` (use tiny for CPU)
   - `REDIS_URL` (use Railway's Redis addon)
3. Deploy

```bash
# Or use Railway CLI
railway login
railway init
railway add --plugin redis
railway up
```

### Render

1. Create a new Web Service from your GitHub repo
2. Set build command: `pip install -e .`
3. Set start command: `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
4. Add environment variables
5. Create a Redis instance and link it

---

## Kubernetes Deployment

### Kubernetes Manifests

**namespace.yaml**
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: meet-transcriber
```

**secrets.yaml**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: meet-transcriber-secrets
  namespace: meet-transcriber
type: Opaque
stringData:
  HUGGINGFACE_ACCESS_TOKEN: "hf_your_token_here"
```

**configmap.yaml**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: meet-transcriber-config
  namespace: meet-transcriber
data:
  WHISPER_MODEL: "base"
  REDIS_URL: "redis://redis:6379/0"
  LOG_LEVEL: "INFO"
  LOG_JSON: "true"
  PRELOAD_MODELS: "true"
```

**redis.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: meet-transcriber
spec:
  replicas: 1
  selector:
    matchLabels:
      app: redis
  template:
    metadata:
      labels:
        app: redis
    spec:
      containers:
      - name: redis
        image: redis:7-alpine
        ports:
        - containerPort: 6379
        resources:
          requests:
            memory: "256Mi"
            cpu: "100m"
          limits:
            memory: "512Mi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: redis
  namespace: meet-transcriber
spec:
  selector:
    app: redis
  ports:
  - port: 6379
    targetPort: 6379
```

**api-deployment.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: meet-transcriber
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
      - name: api
        image: your-registry/meet-transcriber:latest
        ports:
        - containerPort: 8000
        envFrom:
        - configMapRef:
            name: meet-transcriber-config
        - secretRef:
            name: meet-transcriber-secrets
        resources:
          requests:
            memory: "4Gi"
            cpu: "1000m"
            nvidia.com/gpu: 1
          limits:
            memory: "8Gi"
            cpu: "4000m"
            nvidia.com/gpu: 1
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: meet-transcriber
spec:
  selector:
    app: api
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

**worker-deployment.yaml**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: worker
  namespace: meet-transcriber
spec:
  replicas: 1
  selector:
    matchLabels:
      app: worker
  template:
    metadata:
      labels:
        app: worker
    spec:
      containers:
      - name: worker
        image: your-registry/meet-transcriber:latest
        command: ["celery", "-A", "src.worker.celery_app", "worker", "--loglevel=INFO", "--concurrency=1"]
        envFrom:
        - configMapRef:
            name: meet-transcriber-config
        - secretRef:
            name: meet-transcriber-secrets
        resources:
          requests:
            memory: "8Gi"
            cpu: "2000m"
            nvidia.com/gpu: 1
          limits:
            memory: "16Gi"
            cpu: "4000m"
            nvidia.com/gpu: 1
```

**Deploy to Kubernetes**

```bash
kubectl apply -f namespace.yaml
kubectl apply -f secrets.yaml
kubectl apply -f configmap.yaml
kubectl apply -f redis.yaml
kubectl apply -f api-deployment.yaml
kubectl apply -f worker-deployment.yaml

# Check status
kubectl get pods -n meet-transcriber
kubectl logs -f deployment/api -n meet-transcriber
```

---

## Environment & Secrets

### Using AWS Secrets Manager

```bash
# Create secret
aws secretsmanager create-secret \
  --name meet-transcriber/hf-token \
  --secret-string '{"HUGGINGFACE_ACCESS_TOKEN":"hf_your_token"}'

# In your app, use boto3 to retrieve
```

### Using HashiCorp Vault

```bash
# Store secret
vault kv put secret/meet-transcriber hf_token=hf_your_token

# In Kubernetes, use Vault Agent Injector
```

### Using Google Secret Manager

```bash
# Create secret
echo -n "hf_your_token" | gcloud secrets create hf-token --data-file=-

# Grant access
gcloud secrets add-iam-policy-binding hf-token \
  --member="serviceAccount:PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

---

## Monitoring & Logging

### Prometheus + Grafana

Add to your docker-compose for local monitoring:

```yaml
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

### CloudWatch (AWS)

```python
# Add to your logging configuration
import watchtower
import logging

logging.getLogger().addHandler(
    watchtower.CloudWatchLogHandler(log_group="meet-transcriber")
)
```

### Application Metrics

Add FastAPI metrics endpoint:

```python
from prometheus_client import Counter, Histogram, generate_latest
from fastapi import Response

TRANSCRIPTION_REQUESTS = Counter('transcription_requests_total', 'Total transcription requests')
TRANSCRIPTION_DURATION = Histogram('transcription_duration_seconds', 'Transcription duration')

@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

---

## Scaling Considerations

### Horizontal Scaling

```yaml
# Kubernetes HPA
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: worker-hpa
  namespace: meet-transcriber
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: worker
  minReplicas: 1
  maxReplicas: 10
  metrics:
  - type: External
    external:
      metric:
        name: celery_queue_length
      target:
        type: AverageValue
        averageValue: 5
```

### Queue-Based Scaling

Monitor Celery queue length and scale workers accordingly:

```bash
# Get queue length
celery -A src.worker.celery_app inspect active --json | jq 'length'
```

### GPU Sharing

For multiple workers on a single GPU, use NVIDIA MPS:

```bash
# Enable MPS
nvidia-cuda-mps-control -d

# Set memory limits per process
export CUDA_MPS_PINNED_DEVICE_MEM_LIMIT="0=4GB"
```

---

## Cost Optimization

### Spot/Preemptible Instances

**AWS Spot Instances:**
```bash
aws ec2 request-spot-instances \
  --instance-count 1 \
  --type "one-time" \
  --launch-specification file://spot-spec.json
```

**GCP Preemptible VMs:**
```bash
gcloud compute instances create meet-transcriber \
  --preemptible \
  --machine-type n1-standard-4 \
  --accelerator type=nvidia-tesla-t4,count=1
```

### Auto-Shutdown

Shut down GPU instances during low-usage periods:

```bash
# AWS Lambda function to stop instances at night
import boto3

def lambda_handler(event, context):
    ec2 = boto3.client('ec2')
    ec2.stop_instances(InstanceIds=['i-xxxxx'])
```

### Right-Sizing

| Usage Pattern | Recommended Setup |
|---------------|-------------------|
| < 10 jobs/day | CPU instance, tiny model |
| 10-100 jobs/day | Single GPU, base model |
| 100-1000 jobs/day | 2-3 GPU workers, base model |
| > 1000 jobs/day | Auto-scaling GPU cluster |

---

## Troubleshooting

### Common Issues

**GPU not detected:**
```bash
# Check NVIDIA driver
nvidia-smi

# Check Docker GPU access
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi
```

**Out of memory:**
```bash
# Reduce model size
WHISPER_MODEL=tiny

# Or increase instance size
```

**Slow first request:**
```bash
# Enable model preloading
PRELOAD_MODELS=true
```

**Redis connection refused:**
```bash
# Check Redis is running
redis-cli ping

# Check network connectivity
docker network ls
docker network inspect meet-transcript-whisper_default
```

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Redis health
redis-cli ping

# Celery worker health
celery -A src.worker.celery_app inspect ping
```

---

## Security Checklist

- [ ] Use HTTPS in production (SSL/TLS certificates)
- [ ] Store secrets in a secrets manager, not environment files
- [ ] Enable authentication for API endpoints (add API keys or OAuth)
- [ ] Restrict network access with security groups/firewalls
- [ ] Enable audit logging
- [ ] Regularly update dependencies and base images
- [ ] Use non-root user in containers (already configured)
- [ ] Set resource limits to prevent DoS
- [ ] Enable rate limiting for API endpoints
