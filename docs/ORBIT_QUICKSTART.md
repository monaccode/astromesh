# Astromesh Orbit — Quick Start

Get from zero to a production Astromesh stack on GCP in under 15 minutes.

**Prerequisites:**

- Python 3.12+
- [Terraform](https://developer.hashicorp.com/terraform/install) (v1.5+)
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud` CLI)
- A GCP project with billing enabled

---

## Step 1: Install Orbit

```bash
pip install astromesh-orbit[gcp]
```

Verify the installation:

```bash
astromeshctl orbit --help
```

You should see the Orbit subcommands: `init`, `plan`, `apply`, `status`, `destroy`, `eject`.

---

## Step 2: Authenticate with GCP

```bash
gcloud auth login
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

Orbit uses Application Default Credentials for pre-deploy validation. Terraform uses the same credentials for provisioning.

---

## Step 3: Initialize the Configuration

Run the interactive wizard:

```bash
astromeshctl orbit init --provider gcp
```

The wizard walks you through:

1. **GCP project** — auto-detected from `gcloud config` or enter manually
2. **Region** — select from available regions (default: `us-central1`)
3. **Preset** — choose between Starter (~$30/mo) and Pro (~$150/mo)
4. **Review** — confirm the generated settings

This creates `orbit.yaml` in your project root and adds `.orbit/` to `.gitignore`.

To skip the wizard and use a preset directly:

```bash
# Starter preset — minimal resources, single instances
astromeshctl orbit init --provider gcp --preset starter

# Pro preset — auto-scaling, high availability
astromeshctl orbit init --provider gcp --preset pro
```

---

## Step 4: Review the Configuration

Open `orbit.yaml` to inspect and adjust:

```yaml
apiVersion: astromesh/v1
kind: OrbitDeployment
metadata:
  name: my-astromesh
  environment: production

spec:
  provider:
    name: gcp
    project: my-gcp-project-id
    region: us-central1

  compute:
    runtime:
      min_instances: 1
      max_instances: 5
      cpu: "2"
      memory: "2Gi"
    cloud_api:
      min_instances: 1
      max_instances: 3
      cpu: "1"
      memory: "1Gi"
    studio:
      min_instances: 0
      max_instances: 2

  database:
    tier: db-f1-micro
    version: POSTGRES_16
    storage_gb: 10
    high_availability: false

  cache:
    tier: basic
    memory_gb: 1

  secrets:
    provider_keys: true
    jwt_secret: true

  images:
    runtime: fulfarodev/astromesh:latest
    cloud_api: fulfarodev/astromesh-cloud-api:latest
    studio: fulfarodev/astromesh-cloud-studio:latest
```

Edit any values to fit your needs. See [`ORBIT_CONFIGURATION.md`](ORBIT_CONFIGURATION.md) for the full reference.

---

## Step 5: Preview the Deployment

Run `plan` to validate prerequisites and preview what Terraform will create:

```bash
astromeshctl orbit plan
```

Orbit will:

1. **Validate** — check GCP credentials, project access, required APIs
2. **Generate** — render Jinja2 templates into `.orbit/generated/*.tf`
3. **Plan** — run `terraform init` + `terraform plan` and show the resource diff

Example output:

```
Validation
  [PASS] gcloud CLI authenticated
  [PASS] Project 'my-gcp-project-id' exists
  [PASS] Required APIs enabled (5/5)
  [PASS] Sufficient quota

Terraform Plan
  + google_cloud_run_v2_service.runtime
  + google_cloud_run_v2_service.cloud_api
  + google_cloud_run_v2_service.studio
  + google_sql_database_instance.main
  + google_redis_instance.main
  + google_secret_manager_secret.provider_keys
  + google_secret_manager_secret.jwt_secret
  + google_vpc_access_connector.main
  + google_service_account.orbit
  + google_project_iam_member.orbit (4 bindings)

Plan: 13 to add, 0 to change, 0 to destroy.
```

If any validation check fails, Orbit shows clear remediation steps. For example:

```
  [FAIL] API 'sqladmin.googleapis.com' not enabled
         Fix: gcloud services enable sqladmin.googleapis.com
```

---

## Step 6: Deploy

Apply the plan to provision your infrastructure:

```bash
astromeshctl orbit apply
```

Terraform will prompt for confirmation. To skip the prompt:

```bash
astromeshctl orbit apply --auto-approve
```

After a successful apply (typically 5-10 minutes), Orbit displays the endpoints:

```
Deployment complete!

Endpoints:
  Runtime:   https://astromesh-runtime-xxxxx-uc.a.run.app
  Cloud API: https://astromesh-cloud-api-xxxxx-uc.a.run.app
  Studio:    https://astromesh-studio-xxxxx-uc.a.run.app

Environment file: .orbit/orbit.env
```

---

## Step 7: Verify the Deployment

Check the status of all provisioned resources:

```bash
astromeshctl orbit status
```

Output:

```
Resource                    Type                    Status
astromesh-runtime           cloud_run_v2_service    running
astromesh-cloud-api         cloud_run_v2_service    running
astromesh-studio            cloud_run_v2_service    running
astromesh-db                sql_database_instance   running
astromesh-redis             redis_instance          running

State bucket: my-gcp-project-id-astromesh-orbit-state
Last applied: 2026-03-18T14:30:00Z
```

Test the runtime endpoint:

```bash
RUNTIME_URL=$(grep ASTROMESH_CLOUD_RUNTIME_URL .orbit/orbit.env | cut -d= -f2)

curl -s "$RUNTIME_URL/health" | jq .
```

Expected:

```json
{
  "status": "healthy",
  "version": "0.7.0"
}
```

---

## Step 8: Configure Secrets

Orbit creates empty Secret Manager entries for provider keys. Populate them via the GCP Console or `gcloud`:

```bash
# Store your OpenAI key
echo -n "sk-your-openai-key" | gcloud secrets versions add astromesh-provider-keys \
  --data-file=-

# The JWT secret is auto-generated on first deploy — no action needed
```

---

## Destroying the Stack

Tear down all provisioned resources:

```bash
astromeshctl orbit destroy
```

Terraform will prompt for confirmation. To skip:

```bash
astromeshctl orbit destroy --auto-approve
```

The state bucket is NOT deleted by `destroy` — it retains the record of what was torn down. Delete it manually after confirming everything is gone:

```bash
gsutil rm -r gs://my-gcp-project-id-astromesh-orbit-state
```

---

## Ejecting to Standalone Terraform

If you want to manage the infrastructure with Terraform directly, without Orbit:

```bash
astromeshctl orbit eject --output-dir ./terraform
```

This generates a self-contained Terraform directory:

```
terraform/
├── backend.tf          # Points to the existing state bucket (no migration needed)
├── main.tf
├── cloud_run.tf
├── cloud_sql.tf
├── memorystore.tf
├── secrets.tf
├── networking.tf
├── iam.tf
├── variables.tf
├── outputs.tf
└── terraform.tfvars    # All values from orbit.yaml resolved into variables
```

Key properties of ejected files:

- **Same state** — `backend.tf` points to the existing state bucket. No state migration needed.
- **Self-contained** — No Jinja2, no Orbit dependency. Plain HCL.
- **Commented** — Explanatory comments on each resource block.
- **Non-destructive** — Orbit can still run alongside ejected files (`orbit apply` regenerates `.orbit/generated/` independently).

After ejecting, use standard Terraform commands:

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

Note: if you modify the ejected files and apply them directly with `terraform apply`, the state diverges from what Orbit expects. Subsequent `orbit apply` calls will detect drift and warn.

---

## Full Example: Init to Running Stack

A single session from start to finish:

```bash
# Install
pip install astromesh-orbit[gcp]

# Authenticate
gcloud auth login
gcloud auth application-default login
gcloud config set project my-project

# Initialize with starter preset
astromeshctl orbit init --provider gcp --preset starter

# Preview
astromeshctl orbit plan

# Deploy (auto-approve for scripting)
astromeshctl orbit apply --auto-approve

# Verify
astromeshctl orbit status

# Test the runtime
RUNTIME_URL=$(grep ASTROMESH_CLOUD_RUNTIME_URL .orbit/orbit.env | cut -d= -f2)
curl -s "$RUNTIME_URL/health" | jq .

# When done — tear down
astromeshctl orbit destroy --auto-approve
```

---

## What's Next

- **Configuration reference** — See [`ORBIT_CONFIGURATION.md`](ORBIT_CONFIGURATION.md) for every field, type, default, and validation rule
- **Architecture overview** — See [`ORBIT_OVERVIEW.md`](ORBIT_OVERVIEW.md) for the full architecture and multi-cloud vision
- **Connect Cloud Studio** — Point Studio at your deployed Cloud API endpoint to manage agents visually
- **Add provider keys** — Store LLM API keys in Secret Manager so your agents can call models
