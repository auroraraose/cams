#!/bin/bash

# ICICI Financial Data Extraction - Cloud Run Deployment Script
# This script builds and deploys the application to Google Cloud Run

set -e  # Exit on any error

# Load environment variables from .env file
# Load environment variables from .env file
load_env_vars() {
    if [ -f ".env" ]; then
        echo "Loading environment variables from .env file..."
        while read -r line || [ -n "$line" ]; do
            # Skip comments and empty lines
            if [[ "$line" =~ ^# ]] || [[ -z "$line" ]]; then
                continue
            fi
            
            # Remove leading/trailing whitespace from line
            line=$(echo "$line" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
            
            # Allow for "KEY = VALUE" by fixing spaces around the first =
            if [[ "$line" == *"="* ]]; then
                key=$(echo "$line" | cut -d '=' -f 1 | sed -e 's/[[:space:]]*$//')
                value=$(echo "$line" | cut -d '=' -f 2- | sed -e 's/^[[:space:]]*//')
                
                # Strip wrapping quotes from value if present (optional but helpful)
                value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
                
                if [[ -n "$key" ]]; then
                    export "$key=$value"
                fi
            fi
        done < .env
    else
        echo "Warning: .env file not found. Using default values."
    fi
}

# Load environment variables first
load_env_vars

# Configuration - with fallback values if not in .env
PROJECT_ID="${PROJECT:-mb-poc-352009}"  # Uses PROJECT from .env or fallback
SERVICE_NAME="listed-company-credit-assessment"
REGION="${LOCATION:-us-central1}"  # Uses LOCATION from .env or fallback
GCS_BUCKET="${GCS_BUCKET_NAME:-cams-i}"  # Uses GCS_BUCKET_NAME from .env or fallback

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 Financial Data Extraction - Cloud Run Deployment${NC}"
echo "=================================================="

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if required tools are installed
check_requirements() {
    echo -e "${BLUE}🔍 Checking requirements...${NC}"
    
    if ! command -v gcloud &> /dev/null; then
        print_error "Google Cloud CLI is not installed. Please install it first."
        echo "Visit: https://cloud.google.com/sdk/docs/install"
        exit 1
    fi
    
    print_status "All requirements met"
}

# Set GCP project
set_project() {
    echo -e "${BLUE}🔧 Setting up GCP project...${NC}"
    
    if [ "$PROJECT_ID" = "your-gcp-project-id" ]; then
        print_error "Please set PROJECT in your .env file with your actual GCP Project ID"
        print_error "Example: PROJECT=your-actual-project-id"
        exit 1
    fi
    
    echo "Using Project ID: $PROJECT_ID"
    echo "Using Region: $REGION"
    echo "Using GCS Bucket: $GCS_BUCKET"
    
    gcloud config set project $PROJECT_ID
    print_status "Project set to: $PROJECT_ID"
}

# Enable required APIs
enable_apis() {
    echo -e "${BLUE}🔌 Enabling required APIs...${NC}"
    
    gcloud services enable cloudbuild.googleapis.com
    gcloud services enable run.googleapis.com
    
    print_status "APIs enabled"
}

# Deploy to Cloud Run (Cloud Run will build the image automatically)
deploy_service() {
    echo -e "${BLUE}🚀 Deploying to Cloud Run (building from source)...${NC}"
    
    gcloud run deploy $SERVICE_NAME \
        --source . \
        --platform managed \
        --region $REGION \
        --allow-unauthenticated \
        --port 8080 \
        --memory 2Gi \
        --cpu 2 \
        --timeout 3600 \
        --concurrency 80 \
        --max-instances 10 \
        --set-env-vars "PYTHONPATH=/app" \
        --set-env-vars "HOST=0.0.0.0" \
        --set-env-vars "PROJECT=$PROJECT_ID" \
        --set-env-vars "LOCATION=$REGION" \
        --set-env-vars "GCS_BUCKET_NAME=$GCS_BUCKET" \
        --set-env-vars "AS_APP=$AS_APP" \
        --set-env-vars "ASSISTANT_ID=$ASSISTANT_ID"
    
    print_status "Service deployed to Cloud Run"
}

# Get service URL
get_service_url() {
    echo -e "${BLUE}🔗 Getting service URL...${NC}"
    
    SERVICE_URL=$(gcloud run services describe $SERVICE_NAME --region=$REGION --format='value(status.url)')
    
    echo "=================================================="
    print_status "Deployment completed successfully!"
    echo -e "${GREEN}🌐 Your application is available at:${NC}"
    echo -e "${BLUE}$SERVICE_URL${NC}"
    echo "=================================================="
}

# Set environment variables for Cloud Run (if .env exists)
set_env_vars() {
    echo -e "${BLUE}🔧 Environment variables configured from .env file${NC}"
    print_status "PROJECT: $PROJECT_ID"
    print_status "REGION: $REGION" 
    print_status "GCS_BUCKET: $GCS_BUCKET"
    print_status "AS_APP: $AS_APP"
    print_status "ASSISTANT_ID: $ASSISTANT_ID"
    
    print_warning "Remember to manually set sensitive environment variables in Cloud Run console:"
    print_warning "- GEMINI_API_KEY (from your .env file)"
    print_warning "- Any other API keys or secrets"
    
    echo "Visit: https://console.cloud.google.com/run/detail/$REGION/$SERVICE_NAME/variables"
}

# Main deployment flow
main() {
    echo "Starting deployment process..."
    echo ""
    
    check_requirements
    set_project
    enable_apis
    deploy_service
    set_env_vars
    get_service_url
    
    echo ""
    echo -e "${GREEN}🎉 Deployment completed successfully!${NC}"
    echo ""
    echo -e "${YELLOW}Next steps:${NC}"
    echo "1. Set GEMINI_API_KEY in Cloud Run console (check your .env file for the value)"
    echo "2. Verify GCS bucket permissions for: $GCS_BUCKET"
    echo "3. Test the application"
    echo ""
    echo -e "${BLUE}Useful commands:${NC}"
    echo "- View logs: gcloud run logs tail $SERVICE_NAME --region=$REGION"
    echo "- Update service: Re-run this script"
    echo "- Delete service: gcloud run services delete $SERVICE_NAME --region=$REGION"
}

# Handle script arguments
case "${1:-}" in
    "deploy-only")
        check_requirements
        set_project
        deploy_service
        get_service_url
        ;;
    *)
        main
        ;;
esac
